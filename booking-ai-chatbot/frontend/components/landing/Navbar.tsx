import { LeafIcon } from "@/components/common/Icons";
import { ChatOpenButton } from "@/components/landing/ChatOpenButton";
import { navItems } from "@/components/landing/data";
import { Container } from "@/components/ui/Container";

export function Navbar() {
  return (
    <header className="site-header">
      <Container className="nav-container">
        <a className="brand-mark" href="#top" aria-label="Komorebi Spa">
          <span>
            <LeafIcon />
          </span>
          <strong>Komorebi Spa</strong>
        </a>
        <nav className="nav-links" aria-label="Điều hướng chính">
          {navItems.map((item) => (
            <a href={item.href} key={item.href}>
              {item.label}
            </a>
          ))}
        </nav>
        <ChatOpenButton className="nav-cta" variant="secondary">
          Đặt lịch
        </ChatOpenButton>
      </Container>
    </header>
  );
}
