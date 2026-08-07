"use client";

import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

import { CreateAccountDialog } from "./create-account-dialog";

export function NewAccountButton({ label }: { label: string }) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Button
        type="button"
        size="xl"
        onClick={() => setOpen(true)}
        data-action="new-account"
      >
        <Plus className="size-4" aria-hidden />
        {label}
      </Button>
      <CreateAccountDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
