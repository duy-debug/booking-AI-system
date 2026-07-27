import { AppErrorBoundary } from "@/components/common/AppErrorBoundary";
import { ChatApp } from "@/components/chat/ChatApp";

export default function Home() {
  return <AppErrorBoundary><ChatApp /></AppErrorBoundary>;
}
