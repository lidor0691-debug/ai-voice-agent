"use client";

import { MayaCore, ConstellationRing } from "./parts/MayaCore";
import { HeroRecommendationCard } from "./parts/HeroRecommendation";
import { ActivityRail } from "./parts/ActivityRail";
import { VoiceCallsPanel } from "./parts/VoiceCallsPanel";
import { WhatsAppPanel } from "./parts/WhatsAppPanel";
import { LeadPipeline } from "./parts/LeadPipeline";
import { TalkToMayaDock } from "./parts/TalkToMayaDock";
import { HomeNavRail } from "../_shared/HomeNavRail";
import { HomeStatusStrip } from "../_shared/HomeStatusStrip";
import type { WatchData } from "./watch-mock";
import type { Lang } from "../_shared/home-strings";

interface WatchProps {
  data: WatchData;
  lang: Lang;
  onApprove?: () => void;
  onDecline?: () => void;
  onAsk?: (text: string) => void;
}

export function Watch({ data, lang, onApprove, onDecline, onAsk }: WatchProps) {
  return (
    <>
      <HomeNavRail lang={lang} active="watch" user={data.user} />

      {/* ps-[200px] = padding-inline-start: right in RTL, left in LTR — pushes content away from the fixed nav rail */}
      <div className="ps-[200px] h-full flex flex-col">
        <HomeStatusStrip kpis={data.kpis} />

        <main className="flex-1 min-h-0 px-5 py-4 overflow-hidden">
          <div className="grid grid-cols-12 gap-4 h-full">

            {/* Left — activity rail, scrolls independently */}
            <div className="col-span-12 xl:col-span-3 order-3 xl:order-1 overflow-y-auto">
              <ActivityRail
                alerts={data.alerts}
                insights={data.insights}
                wins={data.wins}
                patterns={data.patterns}
                lang={lang}
              />
            </div>

            {/* Center — radar as live operating field, action card overlapping it */}
            <div className="col-span-12 xl:col-span-6 order-1 xl:order-2 relative h-full overflow-hidden">

              {/* Radar field: atmospheric, no box. Sits in the upper ~64% of the column. */}
              <div className="absolute inset-x-0 top-0 bottom-[36%] flex items-center justify-center px-4">
                <div className="relative aspect-square h-full max-h-[460px] max-w-full">
                  {/* Soft radial halo — extends the field beyond the orb */}
                  <div className="pointer-events-none absolute -inset-10 rounded-full bg-[radial-gradient(circle_at_center,rgba(64,196,180,0.10),transparent_62%)]" />
                  <MayaCore />
                  <ConstellationRing orbits={data.orbits} />
                </div>
              </div>

              {/* Vignette: softens the transition where the action card meets the field */}
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[55%] bg-gradient-to-b from-transparent via-[#0b0e13]/35 to-[#0b0e13]/80 z-[5]" />

              {/* Action card: lifted off the bottom edge, sits on the radar field */}
              <div className="absolute inset-x-0 bottom-6 z-10">
                <HeroRecommendationCard
                  hero={data.hero}
                  lang={lang}
                  onApprove={onApprove}
                  onDecline={onDecline}
                />
              </div>
            </div>

            {/* Right — live panels, scrolls independently */}
            <div className="col-span-12 xl:col-span-3 order-2 xl:order-3 flex flex-col gap-3 h-full overflow-y-auto">
              <VoiceCallsPanel calls={data.calls} lang={lang} />
              <WhatsAppPanel threads={data.whatsapp} lang={lang} />
              <LeadPipeline stages={data.leads} lang={lang} />
            </div>
          </div>
        </main>

        <div className="flex-none px-5 pb-4">
          <TalkToMayaDock prompts={data.prompts} lang={lang} onSend={onAsk} />
        </div>
      </div>
    </>
  );
}
