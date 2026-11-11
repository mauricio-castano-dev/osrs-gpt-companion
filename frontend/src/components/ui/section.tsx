import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "./collapsible";
import { GameIcon } from "./game-icon";
export function Section({
  title,
  icon,
  children,
  collapsible = false,
  open = false,
}: {
  title: string;
  icon: string;
  children: ReactNode;
  collapsible?: boolean;
  open?: boolean;
}) {
  if (collapsible)
    return (
      <Collapsible defaultOpen={open} className="feature-card">
        <CollapsibleTrigger className="section-title">
          <GameIcon name={icon} />
          <span>{title}</span>
          <ChevronDown className="ml-auto size-4" />
        </CollapsibleTrigger>
        <CollapsibleContent forceMount className="collapsible-body">
          {children}
        </CollapsibleContent>
      </Collapsible>
    );
  return (
    <section className="feature-card">
      <h2 className="section-title">
        <GameIcon name={icon} />
        {title}
      </h2>
      {children}
    </section>
  );
}
