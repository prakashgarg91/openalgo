/**
 * Question: what should the Algos page look like for a trader who wants to start fast?
 *
 * Two variants on this route, switched by ?variant=
 *   (default) the tabbed, tile-based layout in AlgosVibe
 *   classic   the original single column of cards in AlgosClassic
 * Both read the same data. Delete whichever loses.
 */
import { useSearchParams } from 'react-router'
import AlgosClassic from './AlgosClassic'
import AlgosVibe from './AlgosVibe'

export default function Algos() {
  const [params] = useSearchParams()
  return params.get('variant') === 'classic' ? <AlgosClassic /> : <AlgosVibe />
}
