"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";
import { Settings } from "lucide-react";

const subscribe = () => () => {};
const getSnapshot = () => true;
const getServerSnapshot = () => false;

export function Header() {
  const pathname = usePathname();
  const { resolvedTheme } = useTheme();
  const mounted = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const logoSrc = mounted && resolvedTheme === "dark" ? "/logo-dark.png" : "/logo.png";

  return (
    <header className="border-border bg-card border-b">
      <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center">
            <Image
              src={logoSrc}
              alt="Scribe"
              width={151}
              height={56}
              className="h-10 w-auto"
              priority
              unoptimized
            />
          </Link>
          <nav className="flex items-center gap-1">
            <Link
              href="/"
              className={cn(
                "rounded-md px-3 py-1.5 text-sm transition-colors",
                pathname === "/"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Transcribe
            </Link>
            <Link
              href="/settings"
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors",
                pathname === "/settings"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Settings className="h-3.5 w-3.5" />
              Settings
            </Link>
          </nav>
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}
