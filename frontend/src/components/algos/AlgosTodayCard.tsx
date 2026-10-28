import { useQuery } from '@tanstack/react-query'
import { Bot } from 'lucide-react'
import { Link } from 'react-router'
import { algoQueryKeys, fetchCatalogue } from '@/api/algos'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

/** The dashboard's window onto the Algos page: what is running and what it last decided. */
export function AlgosTodayCard() {
  const catalogue = useQuery({
    queryKey: algoQueryKeys.catalogue(),
    queryFn: fetchCatalogue,
    staleTime: 30_000,
    retry: false,
  })
  if (catalogue.isLoading || catalogue.isError || !catalogue.data) return null
  const mine = catalogue.data.filter((a) => a.deployment)

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Bot className="h-4 w-4" aria-hidden="true" />
          Your algos today
        </CardTitle>
        <Link to="/algos" className="text-sm text-muted-foreground underline">
          {mine.length ? 'Manage' : 'Pick one'}
        </Link>
      </CardHeader>
      <CardContent>
        {mine.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No algo is set up yet. Pick one on the Algos page and watch it in Sandbox first.
          </p>
        ) : (
          <ul className="divide-y">
            {mine.map((algo) => {
              const dep = algo.deployment
              if (!dep) return null
              const last = dep.recent_decisions[0]
              return (
                <li
                  key={algo.id}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm"
                >
                  <span className="font-medium">{algo.name}</span>
                  <Badge
                    variant="outline"
                    className={cn(dep.active ? 'text-emerald-600' : 'text-muted-foreground')}
                  >
                    {dep.active ? 'Active' : 'Stopped'}
                  </Badge>
                  <Badge variant="outline">{dep.mode === 'live' ? 'Live' : 'Sandbox'}</Badge>
                  <span className="min-w-0 flex-1 truncate text-muted-foreground">
                    {last
                      ? `${last.action === 'trade' ? 'Traded' : last.action === 'skip' ? 'Sat out' : 'Problem'}: ${last.reason}`
                      : dep.active
                        ? `Waits for its daily check at ${algo.entry_time}.`
                        : 'Turn it on to start.'}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
