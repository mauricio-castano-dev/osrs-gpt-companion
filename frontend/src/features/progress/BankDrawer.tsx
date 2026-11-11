import { useEffect, useState } from "react";
import {
  Drawer,
  DrawerContent,
  DrawerTitle,
  DrawerDescription,
} from "@/components/ui/drawer";
import { Button } from "@/components/ui/button";
import { useDebounce } from "@/hooks/useDebounce";
import { useQuery } from "@/hooks/useQuery";
import { number } from "@/lib/format";
import type { Items } from "@/types/osrs";
export function BankDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [mounted, setMounted] = useState(false),
    [search, set] = useState("");
  useEffect(() => setMounted(true), []);
  const q = useDebounce(search.trim());
  const result = useQuery<Items>(
    open && q ? "/api/bank?q=" + encodeURIComponent(q) : null,
  );
  const body = (
    <>
      <label className="sr-only" htmlFor="bank-search">
        Buscar objetos del banco e inventario
      </label>
      <input
        id="bank-search"
        maxLength={100}
        type="search"
        value={search}
        onChange={(e) => set(e.target.value)}
        placeholder="Buscar nombre o itemId…"
      />
      <div id="bank-results" aria-live="polite" className="result-stack">
        {!q ? (
          <p className="muted">
            Escribe para buscar objetos en tu banco o inventario.
          </p>
        ) : result.loading ? (
          <p>Buscando…</p>
        ) : result.error ? (
          <p role="alert">{result.error}</p>
        ) : result.data?.ok ? (
          <>
            <h3>
              Banco · {number(result.data.bank?.total_matches)} de{" "}
              {number(result.data.bank?.bank_total_items)} objetos
            </h3>
            {result.data.bank?.items?.map((item, i) => (
              <p className="data-row" key={i}>
                <span>{item.name}</span>
                <b>{number(item.quantity)}</b>
              </p>
            ))}
            {result.data.bank?.truncated && (
              <p className="muted">Primeras 30 coincidencias.</p>
            )}
            <h3>Inventario</h3>
            {result.data.inventory?.map((item, i) => (
              <p className="data-row" key={i}>
                <span>{item.name}</span>
                <b>{number(item.quantity)}</b>
              </p>
            ))}
            {!result.data.bank?.total_matches &&
              !result.data.inventory?.length && <p>Sin coincidencias.</p>}
          </>
        ) : (
          <p>Instantánea no disponible.</p>
        )}
      </div>
      <Button variant="outline" onClick={() => onOpenChange(false)}>
        Cerrar banco
      </Button>
    </>
  );
  // Vaul requires a browser document. The first client render matches this static
  // SSR form; after hydration the same feature is managed by the accessible drawer.
  if (!mounted)
    return (
      <section hidden>
        <h2>Banco & Inventario</h2>
        {body}
      </section>
    );
  return (
    <Drawer open={open} onOpenChange={onOpenChange} autoFocus>
      <DrawerContent className="bank-sheet">
        <DrawerTitle>Banco & Inventario</DrawerTitle>
        <DrawerDescription>
          Consulta local de la instantánea en RAM.
        </DrawerDescription>
        {body}
      </DrawerContent>
    </Drawer>
  );
}
