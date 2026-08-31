import { AppErrorBoundary } from "@/components/common/AppErrorBoundary";
import { ChatWidget } from "@/components/chat/ChatWidget";
import { AiBookingJourney } from "@/components/landing/AiBookingJourney";
import { AssistantSection } from "@/components/landing/AssistantSection";
import { ExperienceSection } from "@/components/landing/ExperienceSection";
import { FaqSection } from "@/components/landing/FaqSection";
import { Footer } from "@/components/landing/Footer";
import { GiftSection } from "@/components/landing/GiftSection";
import { HeroSection } from "@/components/landing/HeroSection";
import { Navbar } from "@/components/landing/Navbar";
import { ServicesSection } from "@/components/landing/ServicesSection";
import { TherapistsSection } from "@/components/landing/TherapistsSection";
import { TestimonialsSection } from "@/components/landing/TestimonialsSection";

// Trang landing chính, ghép các section marketing và mount chatbot popup ở cuối cây UI.
export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <HeroSection />
        <ExperienceSection />
        <ServicesSection />
        <TherapistsSection />
        <TestimonialsSection />
        <GiftSection />
        <AiBookingJourney />
        <AssistantSection />
        <FaqSection />
      </main>
      <Footer />
      <AppErrorBoundary>
        <ChatWidget />
      </AppErrorBoundary>
    </>
  );
}
