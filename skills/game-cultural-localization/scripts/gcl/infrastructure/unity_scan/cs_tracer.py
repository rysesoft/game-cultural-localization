"""Heuristic use-site tracer following LocalizedString loads to reading C# code sites."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cs_expr import _expr, _operand
from .cs_flow import _context, _flow, _helpers, _is_debug, _is_read, _stmt_start, _ternary
from .cs_index import CsCodebaseIndex, _rel
from .cs_lexer import _CsFile

__layer__ = "infrastructure"
__pattern__ = "Graph Tracer"
__owns__ = "LocalizedString field flow tracing, StringChanged handlers, variable read sites and key_trace"

TRACE_NOTE = (
    "Heuristic. Loads, use sites, triggers and loaded_not_shown come from a regex search of the C# code, not from a "
    "compiler. Reflection, UnityEvents, aliases and texts passed on as LocalizedString objects stay invisible, so read "
    "the code before you call a text unused."
)


@dataclass(frozen=True, slots=True)
class _TraceHit:
    """Parameter object carrying one discovered LocalizedString evaluation site."""

    cf: _CsFile
    a0: int
    b0: int
    lo: int
    shape: str
    flow: tuple[str, str, bool]
    via: str
    display: str


class _Tracer:
    """Follows every localized field found in Unity assets to the code that reads its text."""

    def __init__(self, root: Path, limit: int) -> None:
        self.limit = limit
        self._idx = CsCodebaseIndex(root)
        self.files = self._idx.files
        self.by_rel = self._idx.by_rel
        self._field_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._var_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._site_cache: dict[tuple[str, int, str], dict[str, Any]] = {}

    def field_trace(self, cls: str, fld: str, script: _CsFile | None) -> dict[str, Any]:
        """Return loads, direct uses and opaque uses of one localized field."""
        ck = (cls, fld)
        if ck in self._field_cache:
            return self._field_cache[ck]
        res: dict[str, Any] = {"loads": [], "direct": [], "opaque": False}
        self._field_cache[ck] = res
        own = self._idx.family(cls, script)
        refs = self._collect_field_refs(cls, fld, own)
        for cf, a0, b0 in refs:
            self._classify_field_ref(res, own, fld, cf, a0, b0)
        return res

    def _collect_field_refs(self, cls: str, fld: str, own: Sequence[_CsFile]) -> list[tuple[_CsFile, int, int]]:
        refs: list[tuple[_CsFile, int, int]] = []
        rx = re.compile(r"\b" + re.escape(fld) + r"\b")
        for cf in own:
            cf.prepare()
            refs += [(cf, m.start(), m.end()) for m in rx.finditer(cf.masked)]
        decl = self._idx.member_decl(own, fld)
        if decl is not None and decl[2]:
            near = self._idx.with_token(fld) & self._idx.with_token(cls)
            orx = re.compile(r"\.\s*(" + re.escape(fld) + r")\b")
            for i in sorted(near):
                cf = self.files[i]
                if cf not in own:
                    cf.prepare()
                    refs += [(cf, m.start(1), m.end(1)) for m in orx.finditer(cf.masked)]
        return refs

    def _classify_field_ref(self, res: dict[str, Any], own: Sequence[_CsFile], fld: str, cf: _CsFile, a0: int, b0: int) -> None:
        m = cf.masked
        if not _is_read(cf, a0, b0) and not re.match(r"\s*\.", m[b0:b0 + 4]):
            return
        a, b = _operand(cf, a0, b0)
        tail = re.sub(r"^\[.*?\]", "", re.sub(r"\s+", "", m[b0:b]))
        if re.match(r"\??\.GetLocalizedString\(", tail):
            lo, hi, shape = _expr(cf, a, b)
            self._record(res, _TraceHit(cf, a0, b0, lo, shape, _flow(cf, lo, hi), "GetLocalizedString", fld))
        elif re.match(r"\??\.StringChanged$", tail):
            op = re.match(r"\s*([+-]=)", m[b:b + 6])
            if op and op.group(1) == "+=":
                self._subscription(res, cf, b + op.end(), [cf] + [g for g in own if g is not cf])
        elif tail == "":
            if not re.match(r"\s*(?:[!=]=|=(?![=>]))", m[b:b + 6]) and not re.search(r"[!=]=\s*$", m[max(0, a - 6):a]):
                res["opaque"] = True
        elif "GetLocalizedStringAsync" in tail:
            res["opaque"] = True

    def _record(self, res: dict[str, Any], hit: _TraceHit) -> None:
        kind, name, local = hit.flow
        kind = "direct" if kind == "init" else kind
        if kind == "load":
            res["loads"].append({
                "cf": hit.cf, "pos": hit.a0, "var": name, "local": local, "via": hit.via,
                "shape": hit.shape, "when": _ternary(hit.cf, hit.lo),
            })
        elif kind == "return":
            member = name or _context(hit.cf, hit.lo, _stmt_start(hit.cf, hit.lo))[0]
            if member:
                res["loads"].append({
                    "cf": hit.cf, "pos": hit.a0, "var": member, "local": False, "via": "return",
                    "shape": hit.shape, "when": _ternary(hit.cf, hit.lo),
                })
            else:
                res["opaque"] = True
        else:
            res["direct"].append((hit.cf, hit.a0, hit.b0, hit.display))

    def _subscription(self, res: dict[str, Any], cf: _CsFile, k: int, own: Sequence[_CsFile]) -> None:
        m = cf.masked
        lm = re.match(r"\s*(?:\(\s*(?:string\s+)?([A-Za-z_]\w*)\s*\)|([A-Za-z_]\w*))\s*=>\s*", m[k:k + 200])
        if lm:
            body = k + lm.end()
            end = cf.close_of.get(body) if m[body:body + 1] == "{" else None
            param = lm.group(1) or lm.group(2)
            if end is None:
                found = m.find(";", body)
                self._param_flows(res, cf, param, body, len(m) if found < 0 else found, body)
            else:
                self._param_flows(res, cf, param, body, end, 0)
            return
        hm = re.match(r"\s*(?:this\s*\.\s*)?([A-Za-z_]\w*)\s*;", m[k:k + 200])
        if not hm:
            res["opaque"] = True
            return
        rx = re.compile(r"\bvoid\s+" + re.escape(hm.group(1)) + r"\s*\(\s*string\s+([A-Za-z_]\w*)\s*\)\s*(=>|\{)")
        for g in own:
            dm = rx.search(g.prepare().masked)
            if dm:
                if dm.group(2) == "=>":
                    end = g.masked.find(";", dm.end())
                    self._param_flows(res, g, dm.group(1), dm.end(), len(g.masked) if end < 0 else end, dm.end())
                else:
                    self._param_flows(res, g, dm.group(1), dm.end(), g.close_of.get(dm.end() - 1, len(g.masked)), 0)
                return
        res["opaque"] = True

    def _param_flows(self, res: dict[str, Any], cf: _CsFile, param: str, start: int, end: int, floor: int) -> None:
        if param == "_":
            return
        for pm in re.finditer(r"\b" + re.escape(param) + r"\b", cf.masked[start:end]):
            a0, b0 = start + pm.start(), start + pm.end()
            if cf.masked[a0 - 1:a0] == "." or not _is_read(cf, a0, b0):
                continue
            a, b = _operand(cf, a0, b0)
            lo, hi, shape = _expr(cf, a, b)
            self._record(res, _TraceHit(cf, a0, b0, lo, shape, _flow(cf, lo, hi, floor), "StringChanged", param))

    def var_trace(self, load: dict[str, Any], cls: str, own: Sequence[_CsFile]) -> dict[str, Any]:
        """Reads of the variable a text was loaded into."""
        cf, name = load["cf"], load["var"]
        mb = self._idx.method_block(cf, load["pos"])
        local = load["local"] or (
            mb is not None and load["via"] != "return"
            and bool(re.search(r"(?:\bvar|\bstring)\s+" + re.escape(name) + r"\s*[=;]", cf.masked[mb[0]:load["pos"]]))
        )
        if local and mb is not None:
            ck: tuple[Any, ...] = ("local", cf.rel, mb[0], name)
            if ck not in self._var_cache:
                rx = re.compile(r"\b" + re.escape(name) + r"\b")
                sites = [(cf, m.start(), m.end(), name) for m in rx.finditer(cf.masked, load["pos"], mb[1])
                         if cf.masked[m.start() - 1:m.start()] != "." and _is_read(cf, m.start(), m.end())]
                self._var_cache[ck] = {"scope": "local", "sites": sites, "maybe": 0, "display": name}
            return self._var_cache[ck]
        decl = self._idx.member_decl(own, name)
        if load["via"] == "return":
            dcls = decl[3] if decl else cls
            ck = ("member", dcls, name)
            if ck not in self._var_cache:
                self._var_cache[ck] = self._member_reads(own, dcls, name, static=decl[1] if decl else False, shared=True, scope="member")
            return self._var_cache[ck]
        if decl is None:
            ck = ("unknown", cls, name)
            if ck not in self._var_cache:
                self._var_cache[ck] = self._member_reads(own, cls, name, static=False, shared=True, scope="unknown")
            return self._var_cache[ck]
        _dfile, static, shared, dcls = decl
        ck = ("member", dcls, name)
        if ck not in self._var_cache:
            files = list(own) + [g for g in self._idx.class_files(dcls) if g not in own]
            self._var_cache[ck] = self._member_reads(files, dcls, name, static=static, shared=shared, scope="static" if static else "field")
        return self._var_cache[ck]

    def _member_reads(self, own: Sequence[_CsFile], cls: str, name: str, *, static: bool, shared: bool, scope: str) -> dict[str, Any]:
        files = list(own) + ([g for g in self._idx.derived(cls) if g not in own] if shared else [])
        sites: list[tuple[_CsFile, int, int, str]] = []
        maybe = 0
        display = f"{cls}.{name}" if static else name
        rx = re.compile(r"\b" + re.escape(name) + r"\b")
        for cf in files:
            for m in rx.finditer(cf.prepare().masked):
                a0, b0 = m.start(), m.end()
                k = a0 - 1
                while k >= 0 and cf.masked[k].isspace():
                    k -= 1
                if k >= 0 and cf.masked[k] == ".":
                    owner = re.search(r"([A-Za-z_]\w*)\s*\??\s*$", cf.masked[max(0, k - 80):k])
                    if not _is_read(cf, a0, b0):
                        continue
                    if owner and owner.group(1) in ("this", "base", cls):
                        sites.append((cf, a0, b0, display))
                    else:
                        maybe += 1
                elif _is_read(cf, a0, b0):
                    sites.append((cf, a0, b0, display))
        if shared:
            maybe += self._cross_file_reads(files, cls, name, static=static, display=display, sites=sites)
        return {"scope": scope, "sites": sites, "maybe": maybe, "display": display}

    def _cross_file_reads(
        self, seen_files: Sequence[_CsFile], cls: str, name: str, *, static: bool, display: str, sites: list[tuple[_CsFile, int, int, str]],
    ) -> int:
        maybe = 0
        cls_files = self._idx.with_token(cls)
        orx = re.compile(r"(?:\b([A-Za-z_]\w*)\s*\??\s*\.\s*)?\b" + re.escape(name) + r"\b")
        for i in sorted(self._idx.with_token(name)):
            cf = self.files[i]
            if cf in seen_files:
                continue
            for m in orx.finditer(cf.prepare().masked):
                a0, b0 = m.start() + (len(m.group()) - len(name)), m.end()
                if not _is_read(cf, a0, b0):
                    continue
                dotted = "." in m.group()
                if (static and m.group(1) == cls) or (not static and dotted and i in cls_files):
                    sites.append((cf, a0, b0, display))
                elif dotted or static:
                    maybe += 1
        return maybe

    def site(self, cf: _CsFile, a0: int, b0: int, display: str) -> dict[str, Any]:
        ck = (cf.rel, a0, display)
        if ck in self._site_cache:
            return self._site_cache[ck]
        a, b = _operand(cf, a0, b0)
        lo, hi, shape = _expr(cf, a, b)
        method, trigger = _context(cf, lo, _stmt_start(cf, lo))
        when = _ternary(cf, lo)
        trigger = ([when] if when else []) + trigger[:2] if when else trigger
        out: dict[str, Any] = {
            "file": cf.rel, "line": cf.line(a0), "text": cf.line_text(a0),
            "variable": display, "method": method, "trigger": trigger, "concat": bool(shape),
        }
        if shape:
            out["shape"] = shape
        if _is_debug(cf, a0):
            out["debug"] = True
        kind, target, _local = _flow(cf, lo, hi)
        if kind in ("load", "init") and target != display.split(".")[-1]:
            out["assigned_to"] = target
        helpers = _helpers(cf, trigger)
        if helpers:
            out["helpers"] = helpers
        self._site_cache[ck] = out
        return out

    def key_trace(self, usages: Sequence[dict[str, Any]], scripts: dict[tuple[str, str], Path], root: Path) -> dict[str, Any]:
        loads: list[dict[str, Any]] = []
        raw: list[tuple[_CsFile, int, int, str]] = []
        dead = bool(usages)
        for u in usages:
            script = scripts.get((u["class"], u["field"]))
            if not u["class"] or u["class"] == "LocalizeStringEvent" or script is None:
                dead = False
                continue
            first = self.by_rel.get(_rel(script, root))
            ft = self.field_trace(u["class"], u["field"], first)
            if ft["opaque"] or ft["direct"] or not ft["loads"]:
                dead = False
            raw += ft["direct"]
            own = self._idx.family(u["class"], first)
            for ld in ft["loads"]:
                lcls = u["class"] if ld["cf"] in own else self._idx.class_at(ld["cf"], ld["pos"])
                vt = self.var_trace(ld, lcls, own if ld["cf"] in own else self._idx.family(lcls, ld["cf"]))
                rec: dict[str, Any] = {
                    "file": ld["cf"].rel, "line": ld["cf"].line(ld["pos"]),
                    "variable": vt["display"], "via": ld["via"], "scope": vt["scope"],
                }
                if ld["shape"]:
                    rec["shape"] = ld["shape"]
                if ld["when"]:
                    rec["trigger"] = [ld["when"]]
                if rec not in loads:
                    loads.append(rec)
                raw += vt["sites"]
                if vt["sites"] or vt["maybe"] or vt["scope"] in ("unknown", "member"):
                    dead = False
        seen: dict[tuple[str, int, str], tuple[_CsFile, int, int, str]] = {}
        for cf, a0, b0, disp in raw:
            seen.setdefault((cf.rel, cf.line(a0), disp), (cf, a0, b0, disp))
        order = sorted(seen, key=lambda k: (_is_debug(seen[k][0], seen[k][1]), k))
        return {
            "loads": loads, "uses": [self.site(*seen[k]) for k in order[: self.limit]],
            "uses_total": len(order), "loaded_not_shown": dead and bool(loads),
        }


def trace_uses(root: Path, keys: dict[str, dict[str, Any]], scripts: dict[tuple[str, str], Path], limit: int) -> dict[str, Any]:
    """Attach loads, uses, uses_total and loaded_not_shown to every key and return use_trace header."""
    tracer = _Tracer(root, limit)
    for info in keys.values():
        info.update(tracer.key_trace(info["usages"], scripts, root))
    return {
        "heuristic": True, "note": TRACE_NOTE, "code_files": len(tracer.files), "use_sites_per_key": limit,
        "keys_with_uses": sum(1 for i in keys.values() if i["uses"]),
        "loaded_not_shown": sum(1 for i in keys.values() if i["loaded_not_shown"]),
    }
