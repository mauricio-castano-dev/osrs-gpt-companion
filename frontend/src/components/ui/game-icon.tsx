import { cn } from "@/lib/utils";
export function GameIcon({
  name,
  className,
}: {
  name: string;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "game-icon",
        `icon-${name.replace(/[^a-z-]/g, "")}`,
        className,
      )}
    />
  );
}
