"use client";

import { AlertTriangle } from "lucide-react";
import { type ReactNode, useState } from "react";

import { PageTransition } from "@/components/layout/page-transition";
import {
  ConfigurationPanel,
  ConfigurationSection,
} from "@/components/patterns/configuration-panel";
import { ConfirmDialog } from "@/components/patterns/confirm-dialog";
import { FormDialog } from "@/components/patterns/form-dialog";
import { Field } from "@/components/patterns/form-field";
import { MotionList, MotionListItem } from "@/components/patterns/motion-list";
import { StatusFade } from "@/components/patterns/status-fade";
import { SwapLabel } from "@/components/patterns/swap-label";
import { AnimatedNumber } from "@/components/ui/animated-number";
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
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const formatRequests = (value: number) => Math.round(value).toLocaleString();

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
  const [replayKey, setReplayKey] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [showError, setShowError] = useState(false);

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

      <Section title="Badge" description="status tones">
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
              <Badge key={variant} variant={variant}>
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

      <Section
        title="Tooltip"
        description="Context on pointer hover and keyboard focus"
      >
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="soft">Hover or focus</Button>
          </TooltipTrigger>
          <TooltipContent>
            Weights set the expected traffic share while endpoints are eligible.
          </TooltipContent>
        </Tooltip>
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

      <Section
        title="ConfigurationPanel"
        description="Collapsible settings sections with nested content surfaces"
      >
        <ConfigurationPanel>
          <ConfigurationSection
            title="General"
            description="Identity and connection settings."
            defaultOpen
          >
            <Field label="Name" htmlFor="demo-configuration-name">
              <Input
                id="demo-configuration-name"
                defaultValue="Solana primary"
              />
            </Field>
          </ConfigurationSection>
          <ConfigurationSection
            title="Health"
            description="Run an on-demand upstream probe."
          >
            <Button variant="soft">Test connection</Button>
          </ConfigurationSection>
        </ConfigurationPanel>
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

      <Section
        title="Motion"
        description="PageTransition — the arrival played on every route change"
      >
        <div className="flex flex-col gap-4">
          <Row>
            <Button onClick={() => setReplayKey((key) => key + 1)}>
              Replay arrival
            </Button>
          </Row>
          {/* In the app the remount comes from the pathname key; here it is
              forced so the enter can be watched without navigating away. */}
          <PageTransition key={replayKey}>
            <div className="rounded-xl bg-ink-wash p-6">
              <p className="text-sm text-ink-700">
                280ms, emphasized-decelerate, 12px of travel. Turn on the OS
                &ldquo;reduce motion&rdquo; setting and this block should appear
                instantly instead.
              </p>
            </div>
          </PageTransition>
        </div>
      </Section>

      <Section
        title="MotionList"
        description="35ms stagger for div-based collections; the same replay key remounts it"
      >
        <MotionList key={replayKey} className="flex flex-col gap-2">
          {["Ethereum", "Solana", "TRON", "BNB Chain"].map((chain) => (
            <MotionListItem
              key={chain}
              className="rounded-xl bg-ink-wash px-4 py-3 text-sm text-ink-700"
            >
              {chain}
            </MotionListItem>
          ))}
        </MotionList>
      </Section>

      <Section
        title="TableRow enterIndex"
        description="Rows stagger through CSS (opacity only), never motion.tr — see DESIGN.md §7"
      >
        <Table key={replayKey}>
          <TableBody>
            {["endpoint-a", "endpoint-b", "endpoint-c"].map((name, i) => (
              <TableRow key={name} enterIndex={i}>
                <TableCell>{name}</TableCell>
                <TableCell className="text-ink-500">healthy</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <Section
        title="StatusFade"
        description="Empty / error panels fade in on mount — no crossfade against the skeleton"
      >
        <StatusFade
          key={replayKey}
          className="mx-auto flex max-w-prose-narrow flex-col items-center gap-2 py-8 text-center"
        >
          <p className="text-lg font-semibold text-ink-900">No providers yet</p>
          <p className="text-md text-ink-500">
            Connect one to sync its endpoints automatically.
          </p>
        </StatusFade>
      </Section>

      <Section
        title="SwapLabel & FieldMessage"
        description="Button label crossfade and the field hint/error collapse"
      >
        <div className="flex max-w-sm flex-col gap-4">
          <Row>
            <Button onClick={() => setSubmitting((value) => !value)}>
              <SwapLabel swapKey={submitting ? "submitting" : "idle"}>
                {submitting ? "Saving…" : "Save"}
              </SwapLabel>
            </Button>
            <Button variant="ghost" onClick={() => setShowError((v) => !v)}>
              Toggle field error
            </Button>
          </Row>
          <Field
            label="Slug"
            htmlFor="demo-swap-slug"
            hint={showError ? undefined : "Lowercase letters and dashes."}
            error={showError ? "Slug is already taken." : undefined}
          >
            <Input id="demo-swap-slug" defaultValue="prod" />
          </Field>
        </div>
      </Section>

      <Section
        title="AnimatedNumber"
        description="Count-up on a MotionValue — no re-render per frame"
      >
        <Row>
          <span className="text-3xl font-bold tabular-nums text-ink-900">
            <AnimatedNumber
              key={replayKey}
              value={1_284_930}
              format={formatRequests}
            />
          </span>
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
