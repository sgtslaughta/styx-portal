import * as React from "react";

interface SectionHeadProps {
  title: string;
  note?: React.ReactNode;
  action?: React.ReactNode;
  as?: "h1" | "h2" | "h3";
}

export function SectionHead({ title, note, action, as: Tag = "h2" }: SectionHeadProps) {
  return (
    <div className="mb-4 flex items-center gap-3.5">
      <Tag className="whitespace-nowrap text-[15px] font-semibold">{title}</Tag>
      <span className="gold-rule" aria-hidden="true" />
      {note && <small className="whitespace-nowrap text-[13px] text-muted-foreground">{note}</small>}
      {action}
    </div>
  );
}
