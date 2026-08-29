import { Badge } from "@/components/ui/badge";

export function StatePill({
  enabled,
  enabledLabel,
  disabledLabel,
}: {
  enabled: boolean;
  enabledLabel: string;
  disabledLabel: string;
}) {
  return (
    <Badge variant={enabled ? "positive" : "neutral"}>
      {enabled ? enabledLabel : disabledLabel}
    </Badge>
  );
}
