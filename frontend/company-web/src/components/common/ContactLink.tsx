import { Mail } from "lucide-react";
import { siteConfig } from "../../config/site";

interface ContactLinkProps {
  className?: string;
  label?: string;
}

export default function ContactLink({ className = "", label = "협업 문의" }: ContactLinkProps) {
  return (
    <a href={siteConfig.contactHref} className={className}>
      <Mail className="h-4 w-4" />
      <span>{label}</span>
    </a>
  );
}
