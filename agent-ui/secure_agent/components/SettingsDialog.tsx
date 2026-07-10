"use client";

import { useState } from "react";
import { Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import SecurityLevelSelector from "@/components/SecurityLevelSelector";

export default function SettingsDialog() {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9"
          title="Security Settings"
        >
          <Settings className="h-5 w-5" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Global Default Security Level
          </DialogTitle>
          <DialogDescription>
            Sets the server-wide fallback validator level. Per-role policies in
            Admin → Roles take precedence for chat and sanitize for all
            authenticated users.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <SecurityLevelSelector />
        </div>
      </DialogContent>
    </Dialog>
  );
}
