import { useQuery } from '@tanstack/react-query'
import { Loader2, Sprout } from 'lucide-react'
import { algoQueryKeys, fetchIdeaTracker } from '@/api/algos'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

function trialText(numbers: [number, number]): string {
  return numbers[0] === numbers[1] ? String(numbers[0]) : `${numbers[0]} to ${numbers[1]}`
}

export function AutoBuilderPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: algoQueryKeys.ideaTracker(),
    queryFn: fetchIdeaTracker,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sprout className="h-4 w-4" />
          Auto builder
        </CardTitle>
        <CardDescription>
          A disciplined list of every idea tried. It proposes nothing on its own and places no
          order. Live stays locked until an idea passes a forward test, you write its post-mortem
          and you approve.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {isError ? (
          <p role="alert" className="text-sm text-destructive">
            The idea tracker could not be loaded. Check that OpenAlgo is running and try again.
          </p>
        ) : isLoading || !data ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-label="Loading" />
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-muted-foreground">Ideas and settings tried so far</dt>
                <dd className="text-lg font-semibold">{data.trial_count}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Bar a forward result must clear</dt>
                <dd className="text-lg font-semibold">{data.pass_bar.toFixed(6)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Standard errors above zero needed</dt>
                <dd className="text-lg font-semibold">{data.standard_errors_needed.toFixed(1)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Next month with a free idea slot</dt>
                <dd className="text-lg font-semibold">{data.next_free_month}</dd>
              </div>
            </dl>
            <p className="text-xs text-muted-foreground">
              The more ideas tried, the more a good-looking result can be luck, so the bar rises.
            </p>

            <section className="space-y-1">
              <h3 className="text-sm font-medium">Ideas tried</h3>
              {data.ideas.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No idea has been written down through the register yet. Use Register an idea.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-muted-foreground">
                      <tr>
                        <th className="py-1 pr-3 font-normal">Idea</th>
                        <th className="pr-3 font-normal">Registered</th>
                        <th className="pr-3 font-normal">Trial</th>
                        <th className="font-normal">Where it stands</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.ideas.map((idea) => (
                        <tr key={idea.id} className="border-t align-top">
                          <td className="py-1 pr-3">{idea.name}</td>
                          <td className="pr-3">{idea.registered}</td>
                          <td className="pr-3">{trialText(idea.trial_numbers)}</td>
                          <td>
                            {idea.stage}
                            {idea.failed_gates.length > 0 && (
                              <div className="text-xs text-muted-foreground">
                                Missed: {idea.failed_gates.join('; ')}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="space-y-1">
              <h3 className="text-sm font-medium">
                What failed before (read before proposing the next idea)
              </h3>
              {data.lessons.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing has failed yet.</p>
              ) : (
                <ul className="list-disc pl-5 text-sm">
                  {data.lessons.map((l) => (
                    <li key={l.gate}>
                      {l.gate} - missed by {l.ideas_missed}{' '}
                      {l.ideas_missed === 1 ? 'idea' : 'ideas'}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {data.forward_tests.length > 0 && (
              <section className="space-y-1">
                <h3 className="text-sm font-medium">Forward tests in Sandbox mode</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-muted-foreground">
                      <tr>
                        <th className="py-1 pr-3 font-normal">Idea</th>
                        <th className="pr-3 font-normal">State</th>
                        <th className="pr-3 font-normal">Trades done</th>
                        <th className="pr-3 font-normal">To go</th>
                        <th className="font-normal">Net after costs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.forward_tests.map((f, i) => (
                        <tr key={`${f.name}-${i}`} className="border-t">
                          <td className="py-1 pr-3">{f.name}</td>
                          <td className="pr-3">
                            {f.verdict ? `${f.state}, ${f.verdict}` : f.state}
                          </td>
                          <td className="pr-3">{f.completed}</td>
                          <td className="pr-3">{f.trades_to_go ?? '-'}</td>
                          <td>
                            {f.net == null
                              ? '-'
                              : `Rs ${Math.round(f.net).toLocaleString('en-IN')}`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-xs text-muted-foreground">
                  Shadow tests on stored prices. No order is placed and nothing here is a result
                  until a test has ended.
                </p>
              </section>
            )}

            <section className="space-y-1">
              <h3 className="text-sm font-medium">The rules</h3>
              <ul className="list-disc pl-5 text-sm">
                {data.rules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
              <p className="text-sm font-medium">Live gate: locked.</p>
            </section>
          </>
        )}
      </CardContent>
    </Card>
  )
}
