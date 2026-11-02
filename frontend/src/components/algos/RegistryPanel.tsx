import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ClipboardCheck, Loader2 } from 'lucide-react'
import { useState } from 'react'
import {
  algoQueryKeys,
  fetchForwardTests,
  fetchReconciliation,
  fetchRegistry,
  registerIdea,
  savePostMortem,
} from '@/api/algos'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { showToast } from '@/utils/toast'

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'Something went wrong. Please try again.'
}

/** "name = value" lines to an object; a number stays a number, anything else stays text. */
function parseSettings(text: string): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const line of text.split('\n')) {
    const at = line.indexOf('=')
    if (at < 1) continue
    const key = line.slice(0, at).trim()
    const raw = line.slice(at + 1).trim()
    out[key] = raw !== '' && !Number.isNaN(Number(raw)) ? Number(raw) : raw
  }
  return out
}

export function RegistryPanel() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: algoQueryKeys.registry(),
    queryFn: fetchRegistry,
  })
  const { data: forward } = useQuery({
    queryKey: algoQueryKeys.forward(),
    queryFn: fetchForwardTests,
  })
  const { data: reconciliation } = useQuery({
    queryKey: algoQueryKeys.reconciliation(),
    queryFn: fetchReconciliation,
  })
  const [postMortem, setPostMortem] = useState<Record<string, string>>({})
  const [values, setValues] = useState<Record<string, string>>({})
  const [gates, setGates] = useState('')
  const [settings, setSettings] = useState('')
  const [busy, setBusy] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  const set = (key: string, value: string) => setValues((old) => ({ ...old, [key]: value }))

  async function savePost(id: string) {
    setProblem(null)
    try {
      await savePostMortem(id, postMortem[id] ?? '')
      showToast.success('Post-mortem saved.', 'algos')
      setPostMortem((old) => ({ ...old, [id]: '' }))
      await queryClient.invalidateQueries({ queryKey: algoQueryKeys.registry() })
    } catch (error) {
      setProblem(errorText(error))
    }
  }

  async function submit() {
    setBusy(true)
    setProblem(null)
    try {
      await registerIdea({
        ...values,
        gates: gates
          .split('\n')
          .map((g) => g.trim())
          .filter(Boolean),
        params: parseSettings(settings),
      })
      showToast.success('Idea registered. It is frozen and counted.', 'algos')
      setValues({})
      setGates('')
      setSettings('')
      await queryClient.invalidateQueries({ queryKey: algoQueryKeys.registry() })
    } catch (error) {
      setProblem(errorText(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ClipboardCheck className="h-4 w-4" />
          Register an idea
        </CardTitle>
        <CardDescription>
          Write the idea and its tests down before anything runs. It is frozen with a fingerprint
          and counted. It can be tested once, and it can only be rejected or made eligible for a
          forward test in Sandbox mode. A replay on history never proves an edge.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-label="Loading" />
        ) : (
          <>
            <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">Ideas and settings tried so far</dt>
                <dd className="text-lg font-semibold">{data.trial_count}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Bar a forward result must clear</dt>
                <dd className="text-lg font-semibold">{data.pass_bar.toFixed(6)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Next month with a free idea slot</dt>
                <dd className="text-lg font-semibold">{data.next_free_month}</dd>
              </div>
            </dl>

            {data.registrations.length > 0 && (
              <table className="w-full text-left text-sm">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="py-1 pr-3 font-normal">Idea</th>
                    <th className="pr-3 font-normal">Registered</th>
                    <th className="pr-3 font-normal">Trial</th>
                    <th className="font-normal">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.registrations.map((r) => (
                    <tr key={r.id} className="border-t">
                      <td className="py-1 pr-3">{r.name}</td>
                      <td className="pr-3">{r.created_at.slice(0, 10)}</td>
                      <td className="pr-3">
                        {r.trial_numbers[0] === r.trial_numbers[1]
                          ? r.trial_numbers[0]
                          : `${r.trial_numbers[0]} to ${r.trial_numbers[1]}`}
                      </td>
                      <td>{r.intact ? r.status : 'changed after it was frozen'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {data.registrations
              .filter((r) => r.needs_post_mortem)
              .map((r) => (
                <div key={`pm-${r.id}`} className="space-y-1 rounded-md border p-3">
                  <Label htmlFor={`pm-${r.id}`}>
                    Post-mortem for {r.name}: what the test showed, what it cannot show, and what
                    you would do differently
                  </Label>
                  <Textarea
                    id={`pm-${r.id}`}
                    rows={3}
                    value={postMortem[r.id] ?? ''}
                    onChange={(e) => setPostMortem((old) => ({ ...old, [r.id]: e.target.value }))}
                  />
                  <Button size="sm" onClick={() => savePost(r.id)}>
                    Save post-mortem
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    A passed forward test counts toward Live only after this is written.
                  </p>
                </div>
              ))}

            {reconciliation && reconciliation.rows.length > 0 && (
              <div className="space-y-1">
                <h3 className="text-sm font-medium">Sandbox fills against the ledger</h3>
                <table className="w-full text-left text-sm">
                  <thead className="text-muted-foreground">
                    <tr>
                      <th className="py-1 pr-3 font-normal">Week ending</th>
                      <th className="pr-3 font-normal">Ledger credit</th>
                      <th className="pr-3 font-normal">Sandbox credit</th>
                      <th className="pr-3 font-normal">Entry shortfall</th>
                      <th className="font-normal">Exit shortfall</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reconciliation.rows.map((r) => (
                      <tr
                        key={r.expiry}
                        className={r.flagged ? 'border-t font-medium' : 'border-t'}
                      >
                        <td className="py-1 pr-3">{r.expiry}</td>
                        <td className="pr-3">{r.ledger_credit.toFixed(2)}</td>
                        <td className="pr-3">{r.bot_credit.toFixed(2)}</td>
                        <td className="pr-3">
                          {r.entry_shortfall.toFixed(2)}
                          {r.flagged ? ' (look at this week)' : ''}
                        </td>
                        <td>{r.exit_shortfall == null ? '-' : r.exit_shortfall.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs text-muted-foreground">
                  Points per spread; positive means the sandbox did worse than the ledger assumed.
                  Average entry shortfall: {reconciliation.mean_entry_shortfall?.toFixed(2)} points.
                </p>
              </div>
            )}

            {forward && forward.length > 0 && (
              <div className="space-y-1">
                <h3 className="text-sm font-medium">Forward tests in Sandbox mode</h3>
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
                    {forward.map((f) => (
                      <tr key={f.name} className="border-t">
                        <td className="py-1 pr-3">{f.name}</td>
                        <td className="pr-3">{f.verdict ? `${f.state}, ${f.verdict}` : f.state}</td>
                        <td className="pr-3">{f.completed}</td>
                        <td className="pr-3">{f.trades_to_go ?? '-'}</td>
                        <td>
                          {f.net == null ? '-' : `Rs ${Math.round(f.net).toLocaleString('en-IN')}`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs text-muted-foreground">
                  Shadow tests on stored prices. No order is placed and nothing here is a result
                  until a test has ended.
                </p>
              </div>
            )}

            <div className="space-y-3">
              {Object.entries(data.fields).map(([key, hint]) => (
                <div key={key} className="space-y-1">
                  <Label htmlFor={`reg-${key}`}>
                    {key.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())}
                  </Label>
                  <Textarea
                    id={`reg-${key}`}
                    rows={key === 'name' ? 1 : 2}
                    placeholder={hint}
                    value={values[key] ?? ''}
                    onChange={(e) => set(key, e.target.value)}
                  />
                </div>
              ))}
              <div className="space-y-1">
                <Label htmlFor="reg-gates">Gates it must pass (one line each)</Label>
                <Textarea
                  id="reg-gates"
                  rows={4}
                  placeholder="Net profit above zero at the normal and at doubled costs"
                  value={gates}
                  onChange={(e) => setGates(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="reg-settings">Settings, one value each (name = value)</Label>
                <Textarea
                  id="reg-settings"
                  rows={3}
                  placeholder="wing width points = 100"
                  value={settings}
                  onChange={(e) => setSettings(e.target.value)}
                />
              </div>
              {problem && (
                <p role="alert" className="text-sm text-destructive">
                  {problem}
                </p>
              )}
              <Button onClick={submit} disabled={busy}>
                {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                Freeze and count this idea
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
