import * as React from "react";

interface SectionHeadProps {
  title: string;
  note?: React.ReactNode;
  action?: React.ReactNode;
  as?: "h1" | "h2" | "h3";
  /** "page" = admin page title (22px); default = section break (15px). */
  size?: "page" | "section";
}

export function SectionHead({ title, note, action, as: Tag = "h2", size = "section" }: SectionHeadProps) {
  return (
    <div className={size === "page" ? "mb-5 flex flex-wrap items-center gap-x-4 gap-y-1" : "mb-4 flex flex-wrap items-center gap-x-3.5 gap-y-1"}>
      <Tag className={size === "page" ? "whitespace-nowrap text-[22px] leading-8 font-semibold tracking-tight" : "whitespace-nowrap text-[15px] leading-6 font-semibold"}>{title}</Tag>
      <span className="gold-rule" aria-hidden="true" />
      {note && <small className="order-last basis-full text-[13px] text-muted-foreground sm:order-none sm:basis-auto sm:whitespace-nowrap">{note}</small>}
      {action}
    </div>
  );
}
