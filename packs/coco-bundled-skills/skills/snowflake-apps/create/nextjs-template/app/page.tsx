import { Suspense } from "react"
import { SessionCard, SessionCardSkeleton } from "@/components/session-card"
import { TimeCard } from "@/components/time-card"
import { QueryCard } from "@/components/query-card"

// Required: Snowflake is not reachable during docker build.
export const dynamic = "force-dynamic"

export default function Home() {
  return (
    <main className="w-full py-12 px-4">
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Suspense fallback={<SessionCardSkeleton />}>
          <SessionCard />
        </Suspense>
        <TimeCard />
        <QueryCard />
      </div>
    </main>
  )
}
