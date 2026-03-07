import { Header } from "@/components/layout/header";
import { Card, CardHeader, CardContent } from "@/components/ui/card";

function SettingRow({
  label,
  description,
  value,
}: {
  label: string;
  description: string;
  value: string;
}) {
  return (
    <div className="flex items-start justify-between py-4 border-b border-slate-50 last:border-0">
      <div>
        <p className="text-slate-800 text-sm font-medium">{label}</p>
        <p className="text-slate-400 text-xs mt-0.5">{description}</p>
      </div>
      <div className="ml-8 flex-shrink-0">
        <span className="text-slate-600 text-sm font-mono bg-slate-50 border border-slate-200 rounded px-2 py-1">
          {value}
        </span>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <>
      <Header title="הגדרות" subtitle="תצורת מערכת ואינטגרציות" />
      <main className="flex-1 overflow-y-auto p-8 space-y-6 max-w-3xl">
        <Card>
          <CardHeader>
            <h2 className="text-slate-800 font-semibold text-sm">
              Twilio — Voice & SMS
            </h2>
          </CardHeader>
          <CardContent className="divide-y divide-slate-50 py-0">
            <SettingRow
              label="Account SID"
              description="מזהה חשבון Twilio שלך"
              value="AC••••••••••••••••"
            />
            <SettingRow
              label="Phone Number"
              description="מספר הטלפון של Maya AI"
              value="+1 (XXX) XXX-XXXX"
            />
            <SettingRow
              label="Voice Webhook"
              description="URL לשיחות נכנסות"
              value="/voice/incoming"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-slate-800 font-semibold text-sm">
              Make.com — Webhook
            </h2>
          </CardHeader>
          <CardContent className="divide-y divide-slate-50 py-0">
            <SettingRow
              label="Webhook URL"
              description="נשלחות כאן נתוני הלידים"
              value="https://hook.eu1.make.com/••••"
            />
            <SettingRow
              label="Payload Format"
              description="פורמט הנתונים שנשלחים"
              value="JSON"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h2 className="text-slate-800 font-semibold text-sm">
              קול ושפה — Hebrew TTS
            </h2>
          </CardHeader>
          <CardContent className="divide-y divide-slate-50 py-0">
            <SettingRow
              label="Voice Engine"
              description="מנוע ה-TTS של Maya AI"
              value="Amazon Polly"
            />
            <SettingRow
              label="Voice Name"
              description="קול עברי נשי"
              value="Polly.Ayelet"
            />
            <SettingRow
              label="STT Language"
              description="שפת זיהוי דיבור"
              value="he-IL"
            />
          </CardContent>
        </Card>

        <p className="text-slate-400 text-xs text-center">
          לשינוי הגדרות, ערוך את קובץ{" "}
          <code className="bg-slate-100 px-1 rounded">.env</code> בשרת FastAPI
        </p>
      </main>
    </>
  );
}
