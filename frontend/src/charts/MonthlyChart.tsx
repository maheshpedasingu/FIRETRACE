import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { NEUTRAL, PLATFORM_COLORS, PLATFORM_ORDER, TEXT_SECONDARY } from "../lib/colors";
import type { MonthRow, Platform } from "../types/api";

export type MonthlyField = "detections" | "unique_cells" | "frp_sum_mw";

/** Pivot monthly rows to one record per month with a column per platform (null = missing). */
export function pivotMonthly(rows: MonthRow[], field: MonthlyField) {
  const months = [...new Set(rows.map((r) => `${r.year}-${String(r.month).padStart(2, "0")}`))].sort();
  const platforms = PLATFORM_ORDER.filter((p) => rows.some((r) => r.platform === p));
  const data = months.map((month) => {
    const record: Record<string, string | number | null> = { month };
    for (const p of platforms) {
      const row = rows.find(
        (r) => r.platform === p && `${r.year}-${String(r.month).padStart(2, "0")}` === month,
      );
      record[p] = row ? row[field] : null;
    }
    return record;
  });
  return { data, platforms };
}

/** One measure, one y-axis, one line per platform; gaps where coverage is missing. */
export function MonthlyChart({ rows, field, title }: { rows: MonthRow[]; field: MonthlyField; title: string }) {
  const { data, platforms } = pivotMonthly(rows, field);
  return (
    <figure className="rounded-lg border border-[var(--border)] p-3">
      <figcaption className="mb-2 text-sm font-medium">{title}</figcaption>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={NEUTRAL} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="month" stroke={TEXT_SECONDARY} tick={{ fontSize: 11 }} />
          <YAxis stroke={TEXT_SECONDARY} tick={{ fontSize: 11 }} allowDecimals={false} />
          <Tooltip
            contentStyle={{ background: "#1a1a19", border: `1px solid ${NEUTRAL}`, fontSize: 12 }}
            formatter={(value) => (value === null || value === undefined ? "no data" : String(value))}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {platforms.map((p: Platform) => (
            <Line
              key={p}
              type="linear"
              dataKey={p}
              name={p}
              stroke={PLATFORM_COLORS[p]}
              strokeWidth={2}
              dot={{ r: 4 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}
