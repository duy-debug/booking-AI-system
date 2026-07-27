import type { SVGProps } from "react";

function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{children}</svg>;
}

export const SparkIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><path d="m12 3 1.2 4.1L17 9l-3.8 1.9L12 15l-1.2-4.1L7 9l3.8-1.9L12 3Z"/><path d="m19 14 .7 2.3L22 17l-2.3.7L19 20l-.7-2.3L16 17l2.3-.7L19 14Z"/></Icon>;
export const SendIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/></Icon>;
export const CalendarIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></Icon>;
export const ClockIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></Icon>;
export const StoreIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><path d="M4 10v10h16V10M3 10l2-6h14l2 6"/><path d="M8 20v-6h8v6M3 10c1 2 3 2 4.5 0 1 2 3.5 2 4.5 0 1 2 3.5 2 4.5 0 1.5 2 3.5 2 4.5 0"/></Icon>;
export const UserIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></Icon>;
export const RefreshIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><path d="M20 7h-6V1"/><path d="M20 7a9 9 0 1 0 1 8"/></Icon>;
export const CheckIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><path d="m5 12 4 4L19 6"/></Icon>;
export const ChevronIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><path d="m9 18 6-6-6-6"/></Icon>;
export const BotIcon = (p: SVGProps<SVGSVGElement>) => <Icon {...p}><rect x="4" y="7" width="16" height="13" rx="4"/><path d="M12 3v4M8 12h.01M16 12h.01M8 16h8"/></Icon>;
