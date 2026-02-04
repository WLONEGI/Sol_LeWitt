import type { ReactNode } from "react";
import { SidebarProvider } from "@/components/ui/sidebar";

export default function ChatLayout({ children }: { children: ReactNode }) {
  return <SidebarProvider defaultOpen={true}>{children}</SidebarProvider>;
}
