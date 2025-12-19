"""
Theme Unifie - Styles partages pour tous les dashboards
========================================================

Utilisation:
    from utils.theme import apply_theme, COLORS, get_css

    # Dans Streamlit:
    apply_theme()

    # Ou manuellement:
    st.markdown(get_css(), unsafe_allow_html=True)
"""

# ==================== COULEURS ====================

class COLORS:
    """Palette de couleurs unifiee"""

    # Primary
    PRIMARY = "#7c3aed"      # Violet
    SECONDARY = "#00d4ff"    # Cyan
    ACCENT = "#feca57"       # Jaune/Or

    # Status
    BUY = "#00ff88"          # Vert neon
    SELL = "#ff4444"         # Rouge
    NEUTRAL = "#888888"      # Gris
    WARNING = "#feca57"      # Jaune

    # Backgrounds
    BG_DARK = "#0e1117"      # Fond principal
    BG_CARD = "#1a1a2e"      # Fond carte
    BG_CARD_LIGHT = "#16213e" # Fond carte clair
    BG_HOVER = "#2d2d44"     # Hover

    # Text
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#888888"
    TEXT_MUTED = "#666666"

    # Gradients
    GRADIENT_PRIMARY = "linear-gradient(90deg, #00d4ff, #7c3aed)"
    GRADIENT_BUY = "linear-gradient(135deg, #00ff88 0%, #00cc66 100%)"
    GRADIENT_SELL = "linear-gradient(135deg, #ff4444 0%, #cc0000 100%)"
    GRADIENT_CARD = "linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)"
    GRADIENT_DEGEN = "linear-gradient(90deg, #ff6b6b, #feca57, #48dbfb, #ff9ff3)"

    # Degen specific
    PUMP = "#00ff88"
    DUMP = "#ff4444"
    DEGEN = "#ff6b6b"


# ==================== CSS COMMUN ====================

def get_base_css() -> str:
    """CSS de base pour tous les dashboards"""
    return f"""
    <style>
        /* ===== RESET & BASE ===== */
        .main {{ background-color: {COLORS.BG_DARK}; }}

        /* ===== TYPOGRAPHY ===== */
        .main-header {{
            font-size: 2rem;
            font-weight: bold;
            background: {COLORS.GRADIENT_PRIMARY};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            padding: 0.5rem;
            margin-bottom: 1rem;
        }}

        .degen-header {{
            font-size: 2rem;
            font-weight: bold;
            background: {COLORS.GRADIENT_DEGEN};
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            text-align: center;
            padding: 0.5rem;
            margin-bottom: 1rem;
        }}

        /* ===== CARDS ===== */
        .card {{
            background: {COLORS.GRADIENT_CARD};
            border-radius: 10px;
            padding: 1rem;
            margin: 0.5rem 0;
        }}

        .card-profit {{
            border-left: 4px solid {COLORS.BUY};
        }}

        .card-loss {{
            border-left: 4px solid {COLORS.SELL};
        }}

        .price-card {{
            background: {COLORS.GRADIENT_CARD};
            padding: 1rem;
            border-radius: 10px;
            text-align: center;
        }}

        .position-card {{
            background: {COLORS.GRADIENT_CARD};
            border-radius: 10px;
            padding: 1rem;
            margin: 0.5rem 0;
        }}

        .position-card.profit {{ border-left: 4px solid {COLORS.BUY}; }}
        .position-card.loss {{ border-left: 4px solid {COLORS.SELL}; }}

        /* ===== SIGNALS ===== */
        .signal-box {{
            padding: 1rem;
            border-radius: 12px;
            text-align: center;
            margin: 0.5rem 0;
        }}

        .signal-buy {{
            background: rgba(0,255,136,0.15);
            border: 2px solid {COLORS.BUY};
        }}

        .signal-sell {{
            background: rgba(255,68,68,0.15);
            border: 2px solid {COLORS.SELL};
        }}

        .signal-neutral {{
            background: rgba(136,136,136,0.15);
            border: 2px solid {COLORS.NEUTRAL};
        }}

        /* ===== ALERTS ===== */
        .alert {{
            padding: 1rem;
            border-radius: 10px;
            margin: 0.5rem 0;
            font-weight: bold;
        }}

        .alert-pump {{
            background: {COLORS.GRADIENT_BUY};
            color: black;
            animation: pulse 1s infinite;
        }}

        .alert-dump {{
            background: {COLORS.GRADIENT_SELL};
            color: white;
            animation: pulse 1s infinite;
        }}

        .alert-warning {{
            background: rgba(254, 202, 87, 0.2);
            border: 2px solid {COLORS.WARNING};
            color: {COLORS.WARNING};
        }}

        @keyframes pulse {{
            0% {{ transform: scale(1); }}
            50% {{ transform: scale(1.02); }}
            100% {{ transform: scale(1); }}
        }}

        /* ===== BUTTONS ===== */
        .stButton > button {{
            font-size: 1rem !important;
            padding: 0.5rem 1rem !important;
            border-radius: 8px !important;
            transition: all 0.2s !important;
        }}

        .stButton > button:hover {{
            transform: scale(1.02);
        }}

        /* ===== METRICS ===== */
        [data-testid="stMetricValue"] {{
            font-size: 1.5rem !important;
        }}

        [data-testid="stMetricDelta"] {{
            font-size: 0.9rem !important;
        }}

        /* ===== TABLES ===== */
        .dataframe {{
            font-size: 0.9rem !important;
        }}

        /* ===== NAV BAR ===== */
        .nav-bar {{
            display: flex;
            justify-content: space-around;
            background: {COLORS.BG_CARD};
            padding: 0.5rem;
            border-radius: 10px;
            margin: 0.5rem 0;
        }}

        .nav-btn {{
            padding: 0.8rem 1.2rem;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            transition: all 0.2s;
            background: transparent;
            color: white;
        }}

        .nav-btn:hover {{
            background: {COLORS.BG_HOVER};
        }}

        .nav-btn.active {{
            background: {COLORS.GRADIENT_PRIMARY};
        }}

        /* ===== LIVE INDICATOR ===== */
        .live-dot {{
            display: inline-block;
            width: 10px;
            height: 10px;
            background: {COLORS.BUY};
            border-radius: 50%;
            animation: blink 1s infinite;
            margin-right: 5px;
        }}

        @keyframes blink {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.3; }}
        }}

        /* ===== SCORE COLORS ===== */
        .score-positive {{ color: {COLORS.BUY}; font-weight: bold; }}
        .score-negative {{ color: {COLORS.SELL}; font-weight: bold; }}
        .score-neutral {{ color: {COLORS.NEUTRAL}; }}

        /* ===== RESPONSIVE ===== */
        @media (max-width: 768px) {{
            .main-header, .degen-header {{
                font-size: 1.5rem;
            }}
            .card, .position-card {{
                padding: 0.75rem;
            }}
        }}
    </style>
    """


def get_mobile_css() -> str:
    """CSS supplementaire pour mode mobile (sans scroll)"""
    return """
    <style>
        /* Supprimer scrollbars */
        ::-webkit-scrollbar {
            display: none !important;
            width: 0 !important;
            height: 0 !important;
        }
        * {
            scrollbar-width: none !important;
            -ms-overflow-style: none !important;
        }
        html, body, [data-testid="stAppViewContainer"], [data-testid="stVerticalBlock"] {
            overflow: hidden !important;
            max-height: 100vh !important;
        }
        .main .block-container {
            padding: 0.5rem 1rem !important;
            max-height: 100vh !important;
            overflow: hidden !important;
        }
    </style>
    """


def get_css(mobile: bool = False) -> str:
    """Retourne le CSS complet"""
    css = get_base_css()
    if mobile:
        css += get_mobile_css()
    return css


# ==================== STREAMLIT HELPERS ====================

def apply_theme(mobile: bool = False):
    """Applique le theme au dashboard Streamlit"""
    import streamlit as st
    st.markdown(get_css(mobile), unsafe_allow_html=True)


def header(text: str, degen: bool = False):
    """Affiche un header style"""
    import streamlit as st
    css_class = "degen-header" if degen else "main-header"
    st.markdown(f'<p class="{css_class}">{text}</p>', unsafe_allow_html=True)


def signal_box(signal: str, text: str):
    """Affiche une box de signal"""
    import streamlit as st
    css_class = {
        "BUY": "signal-buy",
        "SELL": "signal-sell",
        "STRONG_BUY": "signal-buy",
        "STRONG_SELL": "signal-sell",
    }.get(signal.upper(), "signal-neutral")

    st.markdown(f'<div class="signal-box {css_class}">{text}</div>', unsafe_allow_html=True)


def alert(text: str, alert_type: str = "info"):
    """Affiche une alerte"""
    import streamlit as st
    css_class = {
        "pump": "alert-pump",
        "dump": "alert-dump",
        "warning": "alert-warning",
    }.get(alert_type, "alert")

    st.markdown(f'<div class="alert {css_class}">{text}</div>', unsafe_allow_html=True)


def position_card(symbol: str, entry: float, current: float, pnl: float, pnl_pct: float):
    """Affiche une carte de position"""
    import streamlit as st

    card_class = "profit" if pnl >= 0 else "loss"
    pnl_color = COLORS.BUY if pnl >= 0 else COLORS.SELL

    st.markdown(f"""
    <div class="position-card {card_class}">
        <div style="display: flex; justify-content: space-between;">
            <h3 style="margin: 0; color: white;">{symbol}</h3>
            <span style="color: {pnl_color}; font-size: 1.2rem; font-weight: bold;">
                ${pnl:+.2f} ({pnl_pct:+.1f}%)
            </span>
        </div>
        <div style="color: {COLORS.TEXT_SECONDARY}; margin-top: 0.5rem;">
            Entry: ${entry:.4f} | Current: ${current:.4f}
        </div>
    </div>
    """, unsafe_allow_html=True)


def live_indicator(text: str = "LIVE"):
    """Affiche un indicateur live"""
    import streamlit as st
    st.markdown(f'<span class="live-dot"></span> {text}', unsafe_allow_html=True)


# ==================== PLOTLY THEME ====================

PLOTLY_TEMPLATE = "plotly_dark"

PLOTLY_LAYOUT = {
    "template": PLOTLY_TEMPLATE,
    "paper_bgcolor": COLORS.BG_DARK,
    "plot_bgcolor": COLORS.BG_DARK,
    "font": {"color": COLORS.TEXT_PRIMARY},
    "margin": {"l": 40, "r": 40, "t": 40, "b": 40},
}


def apply_plotly_theme(fig):
    """Applique le theme aux graphiques Plotly"""
    fig.update_layout(**PLOTLY_LAYOUT)
    return fig


# ==================== PAGE CONFIGS ====================

PAGE_CONFIGS = {
    "default": {
        "page_title": "Trading Bot",
        "page_icon": "🎯",
        "layout": "wide",
        "initial_sidebar_state": "expanded"
    },
    "degen": {
        "page_title": "Degen Trading",
        "page_icon": "🔥",
        "layout": "wide",
        "initial_sidebar_state": "expanded"
    },
    "scanner": {
        "page_title": "Crypto Scanner",
        "page_icon": "🔍",
        "layout": "wide",
        "initial_sidebar_state": "expanded"
    },
    "mobile": {
        "page_title": "Trading Bot",
        "page_icon": "🎯",
        "layout": "wide",
        "initial_sidebar_state": "collapsed"
    }
}


def get_page_config(config_name: str = "default") -> dict:
    """Retourne la config de page"""
    return PAGE_CONFIGS.get(config_name, PAGE_CONFIGS["default"])
