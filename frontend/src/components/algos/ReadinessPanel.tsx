import { useQuery } from '@tanstack/react-query'
import { Check, Circle, CircleAlert } from 'lucide-react'
import { Link } from 'react-router'
import { algoQueryKeys, fetchReadiness } from '@/api/algos'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const ICON = { done: Check, todo: CircleAlert, confirm: Circle } as const

export function ReadinessPanel() {
  const readiness = useQuery({
    queryKey: algoQueryKeys.readiness(),
    queryFn: fetchReadiness,
    staleTime: 30_000,
  })
  const data = readiness.data
  if (!data) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">
          {data.ready_for_live ? 'Ready for Live trading' : 'Before you can go Live'}
        </CardTitle>
        <CardDescription>
          Sandbox works as soon as you have an API key. Live also needs these.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {data.steps.map((step) => {
            const Icon = ICON[step.state]
            return (
              <li key={step.id} className="flex items-start gap-2 text-sm">
                <Icon
                  aria-hidden="true"
                  className={cn(
                    'mt-0.5 h-4 w-4 shrink-0',
                    step.state === 'done' && 'text-emerald-600',
                    step.state === 'todo' && 'text-amber-600',
                    step.state === 'confirm' && 'text-muted-foreground'
                  )}
                />
                <div>
                  <span className="font-medium">{step.label}</span>
                  <span className="sr-only">{step.state === 'done' ? ' (done)' : ' (to do)'}</span>
                  <p className="text-muted-foreground">
                    {step.detail}{' '}
                    {step.path && (
                      <Link className="underline" to={step.path}>
                        Open
                      </Link>
                    )}
                  </p>
                </div>
              </li>
            )
          })}
        </ul>
      </CardContent>
    </Card>
  )
}
