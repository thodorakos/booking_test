interface IconProps {
  name: string;
  size?: 12 | 14 | 16 | 18 | 20 | 24;
  className?: string;
}

export function Icon({ name, size = 16, className }: IconProps) {
  const cls = className ? `ic-${size} ${className}` : `ic-${size}`;
  return (
    <svg className={`ic ${cls}`} aria-hidden="true">
      <use href={`#i-${name}`} />
    </svg>
  );
}
