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

      <div className="rtl:pe-[200px] ltr:ps-[200px] min-h-full flex flex-col">
        <HomeStatusStrip kpis={data.kpis} />

        <main className="flex-1 px-6 py-6">
          <div className="grid grid-cols-12 gap-6">
            <div className="col-span-12 xl:col-span-3 order-3 xl:order-1">
              <ActivityRail
                alerts={data.alerts}
                insights={data.insights}
                wins={data.wins}
                patterns={data.patterns}
                lang={lang}
              />
            </div>

            <div className="col-span-12 xl:col-span-6 order-1 xl:order-2 flex flex-col gap-6">
              <div className="relative aspect-[4/3] rounded-2xl bg-surface-1/40 border border-border-subtle overflow-hidden">
                <MayaCore />
                <ConstellationRing orbits={data.orbits} />
              </div>
              <HeroRecommendationCard
                hero={data.hero}
                lang={lang}
                onApprove={onApprove}
                onDecline={onDecline}
              />
            </div>

            <div className="col-span-12 xl:col-span-3 order-2 xl:order-3 flex flex-col gap-4">
              <VoiceCallsPanel calls={data.calls} lang={lang} />
              <WhatsAppPanel threads={data.whatsapp} lang={lang} />
              <LeadPipeline stages={data.leads} lang={lang} />
            </div>
          </div>
        </main>

        <div className="px-6 pb-4">
          <TalkToMayaDock prompts={data.prompts} lang={lang} onSend={onAsk} />
        </div>
      </div>
    </>
  );
}
