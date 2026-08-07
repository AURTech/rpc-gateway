"use client";

import { AlertTriangle } from "lucide-react";
import { type ReactNode, useState } from "react";

import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { FormDialog } from "@/components/patterns/form-dialog";
import { Field } from "@/components/patterns/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-bold tracking-tight">{title}</h2>
        {description ? (
          <p className="text-sm text-ink-500">{description}</p>
        ) : null}
      </div>
      <div className="rounded-xl bg-surface p-6 shadow-section">{children}</div>
    </section>
  );
}

function Row({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center gap-3">{children}</div>;
}

const BUTTON_VARIANTS = [
  "default",
  "secondary",
  "outline",
  "ghost",
  "destructive",
  "link",
  "pill-primary",
  "pill-secondary",
  "soft",
] as const;

const BADGE_VARIANTS = [
  "brand",
  "neutral",
  "positive",
  "warning",
  "danger",
] as const;

export default function ComponentGalleryPage() {
  const [chain, setChain] = useState("ethereum");
  const [formOpen, setFormOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [draftName, setDraftName] = useState("");

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-10 px-8 py-8">
      <header className="flex flex-col gap-1">
        <Badge variant="warning">dev only</Badge>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">
          Component gallery
        </h1>
        <p className="text-sm text-ink-500">
          Primitives and patterns from <code>@/components</code>. This page is
          gated to non-production builds.
        </p>
      </header>

      <Section title="Button" description="variants and sizes">
        <div className="flex flex-col gap-4">
          <Row>
            {BUTTON_VARIANTS.map((variant) => (
              <Button key={variant} variant={variant}>
                {variant}
              </Button>
            ))}
          </Row>
          <Row>
            <Button size="xs">xs</Button>
            <Button size="sm">sm</Button>
            <Button size="default">default</Button>
            <Button size="lg">lg</Button>
            <Button size="xl">xl</Button>
            <Button disabled>disabled</Button>
          </Row>
        </div>
      </Section>

      <Section title="Badge" description="status tones, with optional dot">
        <div className="flex flex-col gap-4">
          <Row>
            {BADGE_VARIANTS.map((variant) => (
              <Badge key={variant} variant={variant}>
                {variant}
              </Badge>
            ))}
          </Row>
          <Row>
            {BADGE_VARIANTS.map((variant) => (
              <Badge key={variant} variant={variant} dot>
                {variant}
              </Badge>
            ))}
          </Row>
        </div>
      </Section>

      <Section title="Input & Textarea" description="default, mono, states">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input placeholder="Default input" />
          <Input mono placeholder="eth_getBalance (mono)" />
          <Input disabled placeholder="Disabled" />
          <Input aria-invalid placeholder="Invalid" />
          <Textarea className="sm:col-span-2" placeholder="Textarea" />
        </div>
      </Section>

      <Section
        title="Select"
        description="Radix select (replaces dropdown hacks)"
      >
        <div className="max-w-xs">
          <Select value={chain} onValueChange={setChain}>
            <SelectTrigger aria-label="Chain">
              <SelectValue placeholder="Select a chain" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ethereum">Ethereum</SelectItem>
              <SelectItem value="solana">Solana</SelectItem>
              <SelectItem value="tron">TRON</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </Section>

      <Section title="Card">
        <Card className="max-w-sm">
          <CardHeader>
            <CardTitle>Card title</CardTitle>
            <CardDescription>Supporting description text.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-ink-700">
              Body content sits here, on the surface token with a section
              shadow.
            </p>
          </CardContent>
          <CardFooter className="gap-2">
            <Button size="sm">Action</Button>
            <Button size="sm" variant="ghost">
              Cancel
            </Button>
          </CardFooter>
        </Card>
      </Section>

      <Section title="Field" description="label + control + hint / error">
        <div className="flex max-w-sm flex-col gap-4">
          <Field label="Name" htmlFor="demo-name" hint="Shown to your team.">
            <Input id="demo-name" placeholder="My gateway" />
          </Field>
          <Field
            label="Slug"
            htmlFor="demo-slug"
            required
            error="Slug is already taken."
          >
            <Input id="demo-slug" aria-invalid defaultValue="prod" />
          </Field>
        </div>
      </Section>

      <Section title="Patterns" description="FormDialog & ConfirmDialog">
        <Row>
          <Button onClick={() => setFormOpen(true)}>Open FormDialog</Button>
          <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
            Open ConfirmDialog
          </Button>
        </Row>
      </Section>

      <FormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        title="Create something"
        description="A standard create form with cancel + submit."
        submitLabel="Create"
        cancelLabel="Cancel"
        canSubmit={draftName.trim().length > 0}
        onSubmit={(event) => {
          event.preventDefault();
          setFormOpen(false);
          setDraftName("");
        }}
      >
        <Field label="Name" htmlFor="demo-form-name" required>
          <Input
            id="demo-form-name"
            value={draftName}
            onChange={(event) => setDraftName(event.target.value)}
            placeholder="Name"
          />
        </Field>
      </FormDialog>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Delete this item?"
        description="This action cannot be undone."
        icon={<AlertTriangle />}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={() => setConfirmOpen(false)}
      />
    </div>
  );
}
