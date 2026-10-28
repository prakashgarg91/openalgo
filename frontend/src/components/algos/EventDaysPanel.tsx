import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarX } from 'lucide-react'
import { useState } from 'react'
import { addEventDay, fetchEventDays, removeEventDay } from '@/api/algos'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

function errorText(error: unknown): string {
  const data = (error as { response?: { data?: { message?: string } } })?.response?.data
  return data?.message || 'Something went wrong. Please try again.'
}

/** Days the trader wants every algo to sit out, such as the budget or a central-bank decision. */
export function EventDaysPanel() {
  const queryClient = useQueryClient()
  const days = useQuery({ queryKey: ['algos', 'events'], queryFn: fetchEventDays })
  const [date, setDate] = useState('')
  const [label, setLabel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const refresh = (next: unknown) => {
    queryClient.setQueryData(['algos', 'events'], next)
    queryClient.invalidateQueries({ queryKey: ['algos', 'regime'] })
    queryClient.invalidateQueries({ queryKey: ['algos', 'chooser'] })
  }

  const add = async () => {
    setError(null)
    try {
      refresh(await addEventDay(date, label))
      setDate('')
      setLabel('')
    } catch (e) {
      setError(errorText(e))
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarX className="h-4 w-4" aria-hidden="true" />
          Days to sit out
        </CardTitle>
        <CardDescription>
          List big scheduled days, such as the budget, a central-bank decision or major results.
          Every algo stands aside on that day and on the trading day before it, because an overnight
          trade would carry into it. OpenAlgo has no event calendar of its own.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="event_date">Day</Label>
            <Input
              id="event_date"
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-44"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="event_label">What is it</Label>
            <Input
              id="event_label"
              value={label}
              maxLength={60}
              placeholder="Union Budget"
              onChange={(e) => setLabel(e.target.value)}
              className="w-56"
            />
          </div>
          <Button onClick={add} disabled={!date || !label.trim()}>
            Add
          </Button>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        {days.data && days.data.length === 0 && (
          <p className="text-sm text-muted-foreground">No days listed.</p>
        )}
        <ul className="divide-y text-sm">
          {days.data?.map((d) => (
            <li key={d.date} className="flex items-center justify-between py-1.5">
              <span>
                <span className="font-mono">{d.date}</span> {d.label}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={async () => refresh(await removeEventDay(d.date))}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
