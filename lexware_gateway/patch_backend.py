"""Restrict the pinned upstream server to exports and bookkeeping vouchers."""
import json
from pathlib import Path
import sys

ALLOWED = {'get-profile','list-contacts','get-contact','get-voucherlist','summarize-vouchers',
           'get-voucher','get-vouchers','get-document','get-document-file','get-voucher-file',
           'get-document-link','download-file','get-payment','create-voucher','update-voucher',
           'upload-voucher-file','upload-file'}

def patch(root):
    target = root/'src/tools/index.ts'
    code = target.read_text()
    before = 'const server = withJsonTextResults(withAnnotationTitles(mcpServer));'
    after = '''const base = withJsonTextResults(withAnnotationTitles(mcpServer));
  const allowed = new Set(%s);
  const server = {
    registerTool: (definition: { name: string }, handler: unknown) => {
      if (allowed.has(definition.name)) {
        return (base.registerTool as Function)(definition, handler);
      }
    },
  } as unknown as McpServer;''' % json.dumps(sorted(ALLOWED))
    if code.count(before) != 1:
        raise RuntimeError('Upstream registration changed; review required')
    target.write_text(code.replace(before, after))
    (root/'src/instructions.ts').write_text('''import type { Capabilities } from "./config.js";
export function buildServerInstructions(_capabilities: Capabilities): string {
  return "Exports and bookkeeping vouchers for Verlag der Spielleute. For 2024, substantive checks use saved 01_Export data and original evidence; live access is limited to exports and documented phase-03 corrections with required state and effect verification. No sales-document creation or invoice corrections are available. update-voucher preserves omitted fields and existing attachments; supplied arrays replace their entire list. Supply the verified version to reject stale updates. Bank-payment allocation, voucher cancellation and changes to locked periods require the Lexware web interface.";
}
''')

if __name__ == '__main__':
    patch(Path(sys.argv[1]))
