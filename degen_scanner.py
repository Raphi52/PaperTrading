"""
Degen Scanner - Detection temps reel des opportunites
=====================================================

Scanne les top tokens par volume et detecte:
- Pumps en cours (volume + price spike)
- Momentum breakouts
- RSI oversold avec volume

Usage:
    python degen_scanner.py          # Mode CLI
    streamlit run degen_scanner.py   # Mode Dashboard
"""
import sys
import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Fix encoding Windows
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

from config.degen_config import degen_config
from signals.degen import DegenAnalyzer, DegenSignal

# Couleurs console
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"


@dataclass
class ScanResult:
    """Resultat du scan d'un token"""
    symbol: str
    price: float
    change_1m: float
    change_5m: float
    change_1h: float
    volume_24h: float
    volume_ratio: float
    rsi: float
    score: int
    signal: str
    signal_type: DegenSignal
    reasons: List[str]
    is_pump: bool
    is_dump: bool
    timestamp: datetime


class DegenScanner:
    """Scanner temps reel pour opportunites degen"""

    def __init__(self, config=None):
        self.config = config or degen_config
        self.analyzer = DegenAnalyzer(config)
        self.running = False
        self.results: List[ScanResult] = []
        self.lock = threading.Lock()

        # Cache
        self._symbols_cache = []
        self._last_symbols_update = 0

    def get_top_symbols(self, limit: int = None) -> List[Dict]:
        """Recupere les top tokens par volume 24h"""
        limit = limit or self.config.max_symbols

        # Cache 60 secondes
        if time.time() - self._last_symbols_update < 60 and self._symbols_cache:
            return self._symbols_cache[:limit]

        try:
            url = "https://api.binance.com/api/v3/ticker/24hr"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Filtrer et trier
            symbols = []
            for item in data:
                symbol = item['symbol']

                # Skip non-USDT pairs
                if not symbol.endswith('USDT'):
                    continue

                # Skip blacklist
                base = symbol.replace('USDT', '')
                if base in self.config.blacklist:
                    continue

                # Skip leveraged tokens
                if any(x in symbol for x in ['UP', 'DOWN', 'BEAR', 'BULL', '2L', '2S', '3L', '3S']):
                    continue

                volume_24h = float(item['quoteVolume'])

                # Min volume filter
                if volume_24h < self.config.min_volume_24h:
                    continue

                symbols.append({
                    'symbol': symbol,
                    'base': base,
                    'price': float(item['lastPrice']),
                    'change_24h': float(item['priceChangePercent']),
                    'volume_24h': volume_24h,
                    'trades_24h': int(item['count'])
                })

            # Trier par volume
            symbols.sort(key=lambda x: x['volume_24h'], reverse=True)

            # Boost favorites
            favorites = [s for s in symbols if s['base'] in self.config.favorites]
            others = [s for s in symbols if s['base'] not in self.config.favorites]
            symbols = favorites + others

            self._symbols_cache = symbols[:limit * 2]  # Cache plus que necessaire
            self._last_symbols_update = time.time()

            return symbols[:limit]

        except Exception as e:
            print(f"{Colors.RED}Error fetching symbols: {e}{Colors.RESET}")
            return self._symbols_cache[:limit] if self._symbols_cache else []

    def fetch_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> pd.DataFrame:
        """Recupere les klines pour un symbole"""
        try:
            url = f"https://api.binance.com/api/v3/klines"
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            if not data:
                return pd.DataFrame()

            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])

            # Convert types
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                df[col] = df[col].astype(float)

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            return df

        except Exception as e:
            return pd.DataFrame()

    def analyze_symbol(self, symbol_data: Dict) -> Optional[ScanResult]:
        """Analyse un symbole"""
        symbol = symbol_data['symbol']

        try:
            # Fetch klines
            df = self.fetch_klines(symbol, self.config.timeframe, 100)

            if df.empty or len(df) < 30:
                return None

            # Analyse degen
            analysis = self.analyzer.analyze(df, symbol)

            # Calculer les changes supplementaires
            change_1h = 0
            if len(df) >= 60:
                change_1h = (df['close'].iloc[-1] - df['close'].iloc[-60]) / df['close'].iloc[-60] * 100

            return ScanResult(
                symbol=symbol_data['base'],
                price=df['close'].iloc[-1],
                change_1m=analysis.price_change_1m,
                change_5m=analysis.price_change_5m,
                change_1h=change_1h,
                volume_24h=symbol_data['volume_24h'],
                volume_ratio=analysis.volume_ratio,
                rsi=analysis.rsi,
                score=analysis.score,
                signal=analysis.signal.name,
                signal_type=analysis.signal,
                reasons=analysis.reasons,
                is_pump=analysis.is_pump,
                is_dump=analysis.is_dump,
                timestamp=datetime.now()
            )

        except Exception as e:
            return None

    def scan_all(self, max_workers: int = 10) -> List[ScanResult]:
        """Scanne tous les tokens en parallele"""
        symbols = self.get_top_symbols()

        if not symbols:
            return []

        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.analyze_symbol, s): s for s in symbols}

            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)

        # Trier par score
        results.sort(key=lambda x: x.score, reverse=True)

        with self.lock:
            self.results = results

        return results

    def get_opportunities(self, min_score: int = 50) -> List[ScanResult]:
        """Retourne les opportunites avec score minimum"""
        with self.lock:
            return [r for r in self.results if r.score >= min_score]

    def get_pumps(self) -> List[ScanResult]:
        """Retourne les pumps detectes"""
        with self.lock:
            return [r for r in self.results if r.is_pump]

    def get_dumps(self) -> List[ScanResult]:
        """Retourne les dumps detectes"""
        with self.lock:
            return [r for r in self.results if r.is_dump]

    def print_results(self, results: List[ScanResult], top_n: int = 20):
        """Affiche les resultats en console"""
        os.system('cls' if os.name == 'nt' else 'clear')

        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}  DEGEN SCANNER - {datetime.now().strftime('%H:%M:%S')}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

        # Pumps section
        pumps = [r for r in results if r.is_pump]
        if pumps:
            print(f"{Colors.BOLD}{Colors.GREEN}  PUMPS DETECTED{Colors.RESET}")
            print(f"  {'-'*40}")
            for r in pumps[:5]:
                print(f"  {Colors.GREEN}{r.symbol:>10}{Colors.RESET} | "
                      f"${r.price:>10.4f} | "
                      f"{Colors.GREEN}+{r.change_1m:>5.1f}%{Colors.RESET} | "
                      f"Vol: {r.volume_ratio:.1f}x | "
                      f"Score: {r.score}")
            print()

        # Dumps section
        dumps = [r for r in results if r.is_dump]
        if dumps:
            print(f"{Colors.BOLD}{Colors.RED}  DUMPS DETECTED{Colors.RESET}")
            print(f"  {'-'*40}")
            for r in dumps[:5]:
                print(f"  {Colors.RED}{r.symbol:>10}{Colors.RESET} | "
                      f"${r.price:>10.4f} | "
                      f"{Colors.RED}{r.change_1m:>5.1f}%{Colors.RESET} | "
                      f"Vol: {r.volume_ratio:.1f}x | "
                      f"Score: {r.score}")
            print()

        # Top opportunities
        print(f"{Colors.BOLD}{Colors.YELLOW}  TOP OPPORTUNITIES{Colors.RESET}")
        print(f"  {'-'*76}")
        print(f"  {'Symbol':>10} | {'Price':>12} | {'1min':>7} | {'5min':>7} | {'Vol':>5} | {'RSI':>4} | {'Score':>5} | Signal")
        print(f"  {'-'*76}")

        for r in results[:top_n]:
            # Color based on signal
            if r.signal_type.value >= 3:
                color = Colors.GREEN
            elif r.signal_type.value <= -3:
                color = Colors.RED
            elif r.signal_type.value > 0:
                color = Colors.CYAN
            elif r.signal_type.value < 0:
                color = Colors.MAGENTA
            else:
                color = Colors.WHITE

            # Format changes
            change_1m_str = f"{r.change_1m:+.1f}%"
            change_5m_str = f"{r.change_5m:+.1f}%"

            if r.change_1m > 0:
                change_1m_str = f"{Colors.GREEN}{change_1m_str}{Colors.RESET}"
            elif r.change_1m < 0:
                change_1m_str = f"{Colors.RED}{change_1m_str}{Colors.RESET}"

            if r.change_5m > 0:
                change_5m_str = f"{Colors.GREEN}{change_5m_str}{Colors.RESET}"
            elif r.change_5m < 0:
                change_5m_str = f"{Colors.RED}{change_5m_str}{Colors.RESET}"

            print(f"  {color}{r.symbol:>10}{Colors.RESET} | "
                  f"${r.price:>11.4f} | "
                  f"{change_1m_str:>16} | "
                  f"{change_5m_str:>16} | "
                  f"{r.volume_ratio:>4.1f}x | "
                  f"{r.rsi:>4.0f} | "
                  f"{r.score:>+5} | "
                  f"{color}{r.signal}{Colors.RESET}")

        print(f"\n  {Colors.CYAN}Scanning {len(results)} tokens | "
              f"Refresh: {self.config.scan_interval}s{Colors.RESET}")
        print(f"  {Colors.YELLOW}Press Ctrl+C to stop{Colors.RESET}\n")

    def run_cli(self):
        """Lance le scanner en mode CLI"""
        self.running = True
        print(f"\n{Colors.BOLD}Starting Degen Scanner...{Colors.RESET}")
        print(f"Scanning top {self.config.max_symbols} tokens by volume")
        print(f"Min volume: ${self.config.min_volume_24h/1e6:.1f}M")
        print(f"Mode: {self.config.trading_mode}")
        print(f"\n{Colors.YELLOW}First scan in progress...{Colors.RESET}\n")

        try:
            while self.running:
                start = time.time()

                # Scan
                results = self.scan_all()

                # Display
                self.print_results(results)

                # Wait
                elapsed = time.time() - start
                sleep_time = max(0, self.config.scan_interval - elapsed)
                time.sleep(sleep_time)

        except KeyboardInterrupt:
            self.running = False
            print(f"\n{Colors.YELLOW}Scanner stopped{Colors.RESET}")


def run_streamlit():
    """Lance le scanner en mode Streamlit dashboard"""
    import streamlit as st
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    st.set_page_config(
        page_title="Degen Scanner",
        page_icon="🔥",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # CSS
    st.markdown("""
    <style>
        .pump-alert {
            background: linear-gradient(135deg, #00ff88 0%, #00cc66 100%);
            color: black;
            padding: 1rem;
            border-radius: 10px;
            margin-bottom: 0.5rem;
            font-weight: bold;
        }
        .dump-alert {
            background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%);
            color: white;
            padding: 1rem;
            border-radius: 10px;
            margin-bottom: 0.5rem;
            font-weight: bold;
        }
        .score-high { color: #00ff88; font-weight: bold; }
        .score-low { color: #ff4444; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("# 🔥 Degen Scanner")
    st.markdown("*Real-time momentum & pump detection*")

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        max_symbols = st.slider("Tokens to scan", 20, 100, 50)
        min_volume = st.number_input("Min volume ($M)", value=5.0, step=1.0)
        min_score = st.slider("Min score for alerts", 0, 100, 50)
        auto_refresh = st.toggle("Auto refresh", value=True)

        if auto_refresh:
            refresh_rate = st.slider("Refresh (seconds)", 5, 60, 10)

        st.divider()
        scan_button = st.button("🔍 Scan Now", type="primary", use_container_width=True)

    # Scanner
    scanner = DegenScanner()
    scanner.config.max_symbols = max_symbols
    scanner.config.min_volume_24h = min_volume * 1_000_000

    # Scan
    if scan_button or 'results' not in st.session_state or auto_refresh:
        with st.spinner(f"Scanning {max_symbols} tokens..."):
            results = scanner.scan_all()
            st.session_state.results = results
            st.session_state.scan_time = datetime.now()

    results = st.session_state.get('results', [])
    scan_time = st.session_state.get('scan_time', datetime.now())

    if not results:
        st.warning("No results. Click 'Scan Now' to start.")
        return

    # Alerts
    pumps = [r for r in results if r.is_pump]
    dumps = [r for r in results if r.is_dump]
    opportunities = [r for r in results if r.score >= min_score and not r.is_pump]

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("🟢 Pumps", len(pumps))
    with col2:
        st.metric("🔴 Dumps", len(dumps))
    with col3:
        st.metric("🎯 Opportunities", len(opportunities))
    with col4:
        st.metric("⏱️ Last Scan", scan_time.strftime("%H:%M:%S"))

    st.divider()

    # Pump alerts
    if pumps:
        st.subheader("🚀 PUMP ALERTS")
        for r in pumps[:5]:
            st.markdown(f"""
            <div class="pump-alert">
                <span style="font-size: 1.5rem;">{r.symbol}</span> |
                ${r.price:.4f} |
                +{r.change_1m:.1f}% (1m) |
                Vol: {r.volume_ratio:.1f}x |
                Score: {r.score}
            </div>
            """, unsafe_allow_html=True)

    # Dump alerts
    if dumps:
        st.subheader("📉 DUMP ALERTS")
        for r in dumps[:5]:
            st.markdown(f"""
            <div class="dump-alert">
                <span style="font-size: 1.5rem;">{r.symbol}</span> |
                ${r.price:.4f} |
                {r.change_1m:.1f}% (1m) |
                Vol: {r.volume_ratio:.1f}x |
                Score: {r.score}
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    # Main table
    st.subheader("📊 All Tokens")

    df = pd.DataFrame([{
        'Symbol': r.symbol,
        'Price': f"${r.price:.4f}" if r.price < 1 else f"${r.price:.2f}",
        '1min': f"{r.change_1m:+.1f}%",
        '5min': f"{r.change_5m:+.1f}%",
        '1h': f"{r.change_1h:+.1f}%",
        'Volume': f"${r.volume_24h/1e6:.1f}M",
        'Vol Ratio': f"{r.volume_ratio:.1f}x",
        'RSI': f"{r.rsi:.0f}",
        'Score': r.score,
        'Signal': r.signal
    } for r in results])

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score",
                min_value=-100,
                max_value=100,
                format="%d"
            )
        }
    )

    # Auto refresh
    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()


if __name__ == "__main__":
    # Detecter si on est lance avec streamlit
    if 'streamlit' in sys.modules:
        run_streamlit()
    else:
        # Mode CLI par defaut
        scanner = DegenScanner()
        scanner.run_cli()
