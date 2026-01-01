'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';

interface HeaderProps {
  prices?: Record<string, number>;
  rightContent?: React.ReactNode;
}

const navItems = [
  { href: '/', label: 'Dashboard' },
  { href: '/positions', label: 'Positions' },
  { href: '/trades', label: 'Trades' },
  { href: '/strategies', label: 'Strategies' },
  { href: '/analytics', label: 'Analytics' },
  { href: '/settings', label: 'Settings' },
];

export default function Header({ prices = {}, rightContent }: HeaderProps) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  return (
    <header className="sticky top-0 z-40 bg-[#0a0a0f]/95 backdrop-blur-sm border-b border-gray-800">
      <div className="max-w-[1600px] mx-auto px-4">
        <div className="flex items-center justify-between h-14">
          <div className="flex items-center gap-6">
            <Link href="/" className="text-xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
              PaperTrading
            </Link>
            <nav className="hidden sm:flex items-center gap-1">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    isActive(item.href)
                      ? 'text-white bg-white/10'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {prices['BTC/USDT'] && (
              <div className="hidden md:flex items-center gap-2 text-sm">
                <span className="text-gray-500">BTC</span>
                <span className="font-mono font-bold">${(prices['BTC/USDT'] || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                <span className="text-gray-500 ml-2">ETH</span>
                <span className="font-mono font-bold">${(prices['ETH/USDT'] || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                <div className="w-px h-6 bg-gray-700 ml-2"></div>
              </div>
            )}
            {rightContent}
            <span className="px-3 py-1.5 rounded-full text-xs font-medium bg-green-500/20 text-green-400 border border-green-500/30">
              Live
            </span>
          </div>
        </div>
      </div>

      {/* Mobile nav */}
      <div className="sm:hidden border-t border-gray-800 overflow-x-auto">
        <nav className="flex items-center gap-1 px-4 py-2">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
                isActive(item.href)
                  ? 'text-white bg-white/10'
                  : 'text-gray-400 hover:text-white hover:bg-white/5'
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
