import { AppErrorBoundary } from "@/components/common/AppErrorBoundary";
import { ChatWidget } from "@/components/chat/ChatWidget";
import { AssistantSection } from "@/components/landing/AssistantSection";
import { ContactSection } from "@/components/landing/ContactSection";
import { ExperienceSection } from "@/components/landing/ExperienceSection";
import { FaqSection } from "@/components/landing/FaqSection";
import { Footer } from "@/components/landing/Footer";
import { HeroSection } from "@/components/landing/HeroSection";
import { Navbar } from "@/components/landing/Navbar";
import { ServicesSection } from "@/components/landing/ServicesSection";
import { TestimonialsSection } from "@/components/landing/TestimonialsSection";

export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <HeroSection />
        <ServicesSection />
        <ExperienceSection />
        <TestimonialsSection />
        <AssistantSection />
        <FaqSection />
        <ContactSection />
      </main>
      <Footer />
      <AppErrorBoundary>
        <ChatWidget />
      </AppErrorBoundary>
    </>
  );
}
