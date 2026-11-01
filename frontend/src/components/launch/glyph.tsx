export function Glyph({ name, icon, size }: { name: string; icon?: string | null; size: number }) {
  const style = { width: size, height: size };
  if (icon) return <img src={icon} alt="" style={style} className="shrink-0 rounded-[9px] object-contain" />;
  return <span aria-hidden style={style} className="grid shrink-0 place-items-center rounded-[9px] bg-[#3b4a54] text-[13px] font-semibold text-white">{name.charAt(0).toUpperCase()}</span>;
}
