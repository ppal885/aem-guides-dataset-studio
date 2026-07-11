import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type { ChatEvalBreakdownResponse, ChatEvalTrendsResponse } from '@/api/chatEval';

const STATUS_COLORS: Record<string, string> = {
  grounded: '#10b981',
  partial: '#f59e0b',
  abstain: '#ef4444',
  conflict: '#a855f7',
  none: '#94a3b8',
};

export function ChatEvalCharts({
  trends,
  breakdown,
}: {
  trends: ChatEvalTrendsResponse | null;
  breakdown: ChatEvalBreakdownResponse | null;
}) {
  if (!trends && !breakdown) return null;

  const trendData = trends?.series ?? [];
  const statusData = breakdown?.by_grounding_status ?? [];
  const domainData = breakdown?.by_source_domain ?? [];
  const ratingData = breakdown?.by_rating ?? [];
  const bucketData = breakdown?.confidence_buckets ?? [];

  return (
    <div className="mt-8 grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Answers & quality (30 days)</CardTitle>
          <CardDescription>Daily volume and average quality score</CardDescription>
        </CardHeader>
        <CardContent className="h-64">
          {trendData.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No trend data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar yAxisId="left" dataKey="answers" fill="#6366f1" name="Answers" opacity={0.35} />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="avg_quality"
                  stroke="#10b981"
                  strokeWidth={2}
                  name="Avg quality"
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Grounding status</CardTitle>
          <CardDescription>How answers were grounded in indexed evidence</CardDescription>
        </CardHeader>
        <CardContent className="h-64">
          {statusData.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No grounding data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusData}
                  dataKey="count"
                  nameKey="label"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  paddingAngle={2}
                >
                  {statusData.map((entry) => (
                    <Cell key={entry.label} fill={STATUS_COLORS[entry.label] || STATUS_COLORS.none} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Source domain</CardTitle>
          <CardDescription>Which RAG corpus supplied evidence</CardDescription>
        </CardHeader>
        <CardContent className="h-64">
          {domainData.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No domain data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={domainData} layout="vertical" margin={{ left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="label" width={100} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#0ea5e9" name="Answers" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Ratings & quality buckets</CardTitle>
          <CardDescription>User feedback and quality score distribution</CardDescription>
        </CardHeader>
        <CardContent className="h-64">
          {ratingData.length === 0 && bucketData.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">No rating data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[...ratingData, ...bucketData.map((b) => ({ label: `Q ${b.label}`, count: b.count }))]}
              >
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill="#8b5cf6" name="Count" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
