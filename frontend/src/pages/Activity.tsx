import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Activity as ActivityIcon,
  AlertTriangle,
  CheckCircle2,
  Info,
  ShieldAlert,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  PageHeader,
  Select,
  Skeleton,
} from "../components/ui";
import { apiClient } from "../lib/api";
import { formatRelative } from "../lib/utils";

const levelIcons = {
  info: <Info className="h-3.5 w-3.5 text-accent" />,
  success: <CheckCircle2 className="h-3.5 w-3.5 text-success" />,
  warning: <AlertTriangle className="h-3.5 w-3.5 text-warning" />,
  error: <ShieldAlert className="h-3.5 w-3.5 text-danger" />,
};

export function ActivityPage() {
  const queryClient = useQueryClient();
  const [level, setLevel] = useState("");
  const [category, setCategory] = useState("");

  const activity = useInfiniteQuery({
    queryKey: ["activity", level, category],
    queryFn: ({ pageParam }) =>
      apiClient.activity({
        limit: 100,
        before_id: pageParam ?? undefined,
        level: level || undefined,
        category: category || undefined,
      }),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_before_id,
  });

  const clear = useMutation({
    mutationFn: apiClient.clearActivity,
    onSuccess: () => {
      toast.success("Activity cleared");
      void queryClient.invalidateQueries({ queryKey: ["activity"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not clear"),
  });

  const items = activity.data?.pages.flatMap((page) => page.activity) ?? [];

  return (
    <div className="animate-in">
      <PageHeader
        title="Activity"
        description="Every scan, review, import and error — newest first."
        actions={
          <Button
            variant="outline"
            icon={<Trash2 className="h-4 w-4" />}
            onClick={() => {
              if (window.confirm("Clear the activity log? This cannot be undone.")) clear.mutate();
            }}
            loading={clear.isPending}
          >
            Clear log
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select className="w-40" value={level} onChange={(event) => setLevel(event.target.value)}>
          <option value="">All levels</option>
          <option value="info">Info</option>
          <option value="success">Success</option>
          <option value="warning">Warning</option>
          <option value="error">Error</option>
        </Select>
        <Select className="w-44" value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="">All categories</option>
          <option value="scan">Scans</option>
          <option value="review">Reviews</option>
          <option value="import">Imports</option>
          <option value="duplicate">Duplicates</option>
          <option value="general">General</option>
        </Select>
      </div>

      {activity.isLoading && <Skeleton className="h-64 w-full" />}

      {!activity.isLoading && items.length === 0 && (
        <Card>
          <EmptyState
            icon={<ActivityIcon className="h-5 w-5" />}
            title="Nothing logged yet"
            description="Once Beetser scans an origin, activity shows up here."
          />
        </Card>
      )}

      <div className="space-y-1.5">
        {items.map((item) => (
          <Card key={item.id} className="p-3">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 shrink-0">
                {levelIcons[item.level as keyof typeof levelIcons] ?? levelIcons.info}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs leading-relaxed text-fg">{item.message}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-muted">
                  <span>{formatRelative(item.ts)}</span>
                  <Badge>{item.category}</Badge>
                  {item.origin_name && <span>· {item.origin_name}</span>}
                  {item.job_id && <span className="font-mono">· job {item.job_id.slice(0, 8)}</span>}
                </div>
                {Boolean(item.detail) && (
                  <details className="mt-1.5">
                    <summary className="cursor-pointer text-[10px] text-accent">Details</summary>
                    <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-surface-2 p-2 font-mono text-[10px] text-muted">
                      {JSON.stringify(item.detail, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {activity.hasNextPage && (
        <div className="mt-4 flex justify-center">
          <Button
            variant="secondary"
            onClick={() => void activity.fetchNextPage()}
            loading={activity.isFetchingNextPage}
          >
            Load older
          </Button>
        </div>
      )}
    </div>
  );
}
