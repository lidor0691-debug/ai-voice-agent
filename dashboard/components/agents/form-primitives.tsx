import { CheckCircle } from "lucide-react";

export function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-200 mb-1.5">
        {required && <span className="text-brand-400 ml-1">*</span>}
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{hint}</p>}
    </div>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors"
    />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors resize-none"
    />
  );
}

export function Select({
  options,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  options: { value: string; label: string }[];
}) {
  return (
    <select
      {...props}
      className="w-full bg-surface-3 border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-brand-600 focus:border-brand-600 transition-colors"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value} className="bg-surface-3">
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function StepIndicator({
  currentStep,
  steps,
}: {
  currentStep: number;
  steps: { number: number; label: string }[];
}) {
  return (
    <div className="flex items-start justify-center gap-1 mb-8">
      {steps.map((step, idx) => {
        const done = step.number < currentStep;
        const active = step.number === currentStep;
        return (
          <div key={step.number} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5 w-20">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                  done
                    ? "bg-emerald-500 text-white"
                    : active
                    ? "bg-brand-600 text-white ring-2 ring-brand-400/30"
                    : "bg-surface-3 text-gray-500 border border-border"
                }`}
              >
                {done ? <CheckCircle className="w-4 h-4" /> : step.number}
              </div>
              <span
                className={`text-xs text-center leading-tight ${
                  active ? "text-white font-medium" : "text-gray-600"
                }`}
              >
                {step.label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={`h-px w-6 mb-5 ${
                  step.number < currentStep ? "bg-emerald-500" : "bg-border"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
