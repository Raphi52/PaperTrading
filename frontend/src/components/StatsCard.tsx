'use client';

interface StatsCardProps {
  title: string;
  value: string;
  subtitle?: string;
  positive?: boolean;
}

export function StatsCard({ title, value, subtitle, positive }: StatsCardProps) {
  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      <p className="text-gray-400 text-sm mb-1">{title}</p>
      <p className={`text-2xl font-bold ${
        positive === undefined ? 'text-white' : positive ? 'text-green-400' : 'text-red-400'
      }`}>
        {value}
      </p>
      {subtitle && (
        <p className={`text-sm mt-1 ${
          positive === undefined ? 'text-gray-400' : positive ? 'text-green-400/70' : 'text-red-400/70'
        }`}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
