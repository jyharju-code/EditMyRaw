"""cli.py — command line for EditMyRaw (edit / key / web)."""

from __future__ import annotations

import argparse
import sys

from . import config, pipeline


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="editmyraw", description="Gemini-guided RAW/JPG editing.")
    sub = parser.add_subparsers(dest="cmd")

    e = sub.add_parser("edit", help="Edit one or more images (default).")
    e.add_argument("--inputs", nargs="+", required=True, help="Images / folder / glob.")
    e.add_argument("--out", default="exports", help="Output folder.")
    e.add_argument("--reference", help="Reference image (for example/combo).")
    e.add_argument("--workflow", choices=["prompt", "example", "combo"], default="prompt")
    e.add_argument("--mode", choices=["faithful", "creative"], default="faithful")
    e.add_argument("--prompt", default="")
    e.add_argument("--skin", choices=["face", "skin", "none"], default="face")
    e.add_argument("--format", dest="fmt", choices=["jpg", "tiff"], default="jpg")
    e.add_argument("--quality", type=int, default=95)
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--generative", action="store_true", help="Allow generative edit (creative).")
    e.add_argument("--no-consistency", action="store_true", help="Disable batch consistency sparring.")
    e.add_argument("--rounds", type=int, default=2)

    k = sub.add_parser("key", help="Manage the local API key.")
    k.add_argument("--set", dest="set_key")
    k.add_argument("--show", action="store_true")
    k.add_argument("--clear", action="store_true")

    sub.add_parser("web", help="Launch the browser GUI.")

    args = parser.parse_args(argv)

    if args.cmd == "web":
        from .server import main as web_main
        web_main()
        return

    if args.cmd == "key":
        if args.set_key:
            config.save_api_key(args.set_key)
            print("Key saved to", config.CONFIG_FILE)
        elif args.clear:
            config.clear_api_key()
            print("Key cleared.")
        status = config.key_status()
        print(f"Key: {status['masked'] or 'not set'} (source: {status['source']})")
        return

    if args.cmd in (None, "edit"):
        if args.cmd is None:
            parser.print_help()
            return
        inputs = pipeline.expand_inputs(args.inputs)
        if not inputs:
            sys.exit("No supported input images.")
        print(f"{len(inputs)} image(s) | workflow={args.workflow} mode={args.mode} skin={args.skin}")

        def progress(fr, m):
            sys.stdout.write(f"\r[{int(fr*100):3d}%] {m:<58}")
            sys.stdout.flush()

        res = pipeline.run(
            inputs=inputs, out_dir=args.out, workflow=args.workflow, mode=args.mode,
            prompt=args.prompt, reference=args.reference, skin_mode=args.skin, fmt=args.fmt,
            quality=args.quality, dry_run=args.dry_run, allow_generative=args.generative,
            batch_consistency=not args.no_consistency, consistency_rounds=args.rounds,
            progress=progress,
        )
        print()
        for line in res["gemini_log"]:
            print("  AI:", line)
        print(f"Done: {res['count']} image(s) -> {res['out_dir']}")
        if res["zip_path"]:
            print("ZIP:", res["zip_path"])


if __name__ == "__main__":
    main()
