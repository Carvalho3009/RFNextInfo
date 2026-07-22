// Resolve selected strings and their code references in libUnreal.so.
//@category RFNext

import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class RFNextOodleConfigAnalyzer extends GhidraScript {
    private static class TargetHit {
        final String target;
        final Address address;

        TargetHit(String target, Address address) {
            this.target = target;
            this.address = address;
        }
    }

    private static final String[] TARGETS = {
        "ServerDictionary",
        "ClientDictionary",
        "bEnableOodle",
        "net.OodleMinSizeForCompression",
        "net.OodleClientEnableMode",
        "net.OodleServerEnableMode",
        "PacketHandlerComponents",
        "EncryptionComponent",
        "EncryptionAck",
        "EncryptionToken",
        "Received compressed packet, but no dictionary is present for decompression.",
        "Specify both Server/Client dictionaries for Oodle compressor in DefaultEngine.ini"
    };

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException(
                "Usage: RFNextOodleConfigAnalyzer.java <report-path> [max-functions] [targets-file]");
        }

        Path reportPath = Paths.get(args[0]).toAbsolutePath();
        int maxFunctions = args.length > 1 ? Integer.parseInt(args[1]) : 120;
        List<String> targets = loadTargets(args.length > 2 ? args[2] : null);
        if (reportPath.getParent() != null) {
            Files.createDirectories(reportPath.getParent());
        }

        Map<Address, Set<String>> functions = new LinkedHashMap<>();
        Map<String, List<Address>> occurrences = new LinkedHashMap<>();
        Map<String, List<String>> references = new LinkedHashMap<>();
        Map<Long, List<TargetHit>> hitsByPage = new LinkedHashMap<>();

        for (String target : targets) {
            List<Address> hits = findAll(target.getBytes(StandardCharsets.US_ASCII));
            hits.addAll(findAll(target.getBytes(StandardCharsets.UTF_16LE)));
            occurrences.put(target, hits);
            for (Address hit : hits) {
                long page = hit.getOffset() & ~0xfffL;
                hitsByPage.computeIfAbsent(page, key -> new ArrayList<>())
                    .add(new TargetHit(target, hit));
            }

            List<String> targetReferences = new ArrayList<>();
            for (Address hit : hits) {
                collectReferences(target, hit, hit, "exact", targetReferences, functions);
                Address page = toAddr(hit.getOffset() & ~0xfffL);
                if (!page.equals(hit)) {
                    collectReferences(target, hit, page, "page", targetReferences, functions);
                }
            }
            references.put(target, targetReferences);
        }

        if ("AARCH64".equalsIgnoreCase(
                currentProgram.getLanguage().getProcessor().toString())) {
            scanAdrpAddPairs(hitsByPage, references, functions);
        }
        if (args.length <= 2) {
            addKnownSeed(0x07daca1cL, "known Oodle dictionary config loader", functions);
            addKnownSeed(0x07dacde4L, "known Oodle dictionary initializer", functions);
        }
        else {
            addKnownSeed(0x05bdfcecL, "RFExchangeBuySlot metadata", functions);
            addKnownSeed(0x05be0dd0L, "RFExchangeItemSlot metadata", functions);
            addKnownSeed(0x05be195cL, "RFExchangeSellSlot metadata", functions);
            addKnownSeed(0x05be21c8L, "RFExchangeTransactionSlot metadata", functions);
            addKnownSeed(0x05cedcb8L, "RFPanelExchangeMain metadata", functions);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        decompiler.setSimplificationStyle("decompile");
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("Decompiler: " + decompiler.getLastMessage());
        }

        int completed = 0;
        try (BufferedWriter out = Files.newBufferedWriter(reportPath, StandardCharsets.UTF_8)) {
            out.write("# RF Online NEXT - selected string xrefs\n\n");
            out.write("Generated: " + Instant.now() + "\n\n");
            out.write("- Program: `" + currentProgram.getName() + "`\n");
            out.write("- Image base: `" + currentProgram.getImageBase() + "`\n");
            out.write("- Candidate functions: " + functions.size() + "\n\n");

            out.write("## String occurrences and references\n\n");
            for (String target : targets) {
                out.write("### `" + target + "`\n\n");
                List<Address> hits = occurrences.get(target);
                if (hits.isEmpty()) {
                    out.write("- No occurrence found.\n\n");
                    continue;
                }
                for (Address hit : hits) {
                    out.write("- Occurrence: `" + hit + "`\n");
                }
                List<String> refs = references.get(target);
                if (refs.isEmpty()) {
                    out.write("- No direct Ghidra reference found.\n");
                }
                else {
                    for (String reference : refs) {
                        out.write("- Reference: `" + reference + "`\n");
                    }
                }
                out.write("\n");
            }

            for (Map.Entry<Address, Set<String>> entry : functions.entrySet()) {
                if (completed >= maxFunctions || monitor.isCancelled()) {
                    break;
                }
                Function function = currentProgram.getFunctionManager().getFunctionAt(entry.getKey());
                if (function == null) {
                    continue;
                }
                completed++;
                monitor.setMessage("RFNext string xrefs " + completed + "/" + maxFunctions +
                    ": " + function.getName());
                println("[" + completed + "] " + function.getName() + " @ " +
                    function.getEntryPoint());

                out.write("## " + function.getName() + " @ `" + function.getEntryPoint() + "`\n\n");
                out.write("Reasons: " + String.join("; ", entry.getValue()) + "\n\n");
                out.write("```c\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    out.write(result.getDecompiledFunction().getC());
                }
                else {
                    out.write("/* DECOMPILE FAILED: " + sanitize(result.getErrorMessage()) + " */\n");
                }
                out.write("\n```\n\n");
                out.flush();
            }

            out.write("## Run summary\n\n");
            out.write("- Decompiled functions: " + completed + "\n");
            out.write("- Candidate functions: " + functions.size() + "\n");
            out.write("- Cancelled: " + monitor.isCancelled() + "\n");
        }
        finally {
            decompiler.dispose();
        }

        println("Report written to " + reportPath);
    }

    private List<String> loadTargets(String fileName) throws Exception {
        List<String> targets = new ArrayList<>();
        if (fileName == null) {
            for (String target : TARGETS) {
                targets.add(target);
            }
            return targets;
        }
        for (String line : Files.readAllLines(Paths.get(fileName), StandardCharsets.UTF_8)) {
            String target = line.trim();
            if (!target.isEmpty() && !target.startsWith("#")) {
                targets.add(target);
            }
        }
        if (targets.isEmpty()) {
            throw new IllegalArgumentException("No targets in " + fileName);
        }
        return targets;
    }

    private List<Address> findAll(byte[] bytes) throws Exception {
        List<Address> hits = new ArrayList<>();
        Address cursor = currentProgram.getMinAddress();
        Address maximum = currentProgram.getMaxAddress();
        while (cursor != null && cursor.compareTo(maximum) <= 0 && !monitor.isCancelled()) {
            Address hit = currentProgram.getMemory().findBytes(cursor, bytes, null, true, monitor);
            if (hit == null || hit.compareTo(maximum) > 0) {
                break;
            }
            hits.add(hit);
            try {
                cursor = hit.add(1);
            }
            catch (Exception end) {
                break;
            }
        }
        return hits;
    }

    private void addDirectCallers(Function target, Map<Address, Set<String>> functions,
            String reason) {
        ReferenceIterator iterator = currentProgram.getReferenceManager()
            .getReferencesTo(target.getEntryPoint());
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            if (!reference.getReferenceType().isCall()) {
                continue;
            }
            Function caller = currentProgram.getFunctionManager()
                .getFunctionContaining(reference.getFromAddress());
            if (caller != null) {
                functions.computeIfAbsent(caller.getEntryPoint(), key -> new LinkedHashSet<>())
                    .add(reason + " at " + reference.getFromAddress());
            }
        }
    }

    private void collectReferences(String target, Address hit, Address referenceTarget,
            String kind, List<String> targetReferences,
            Map<Address, Set<String>> functions) {
        ReferenceIterator iterator = currentProgram.getReferenceManager()
            .getReferencesTo(referenceTarget);
        while (iterator.hasNext()) {
            Reference reference = iterator.next();
            Address from = reference.getFromAddress();
            Function owner = currentProgram.getFunctionManager().getFunctionContaining(from);
            String ownerText = owner == null ? "<outside function>" :
                owner.getName() + " @ " + owner.getEntryPoint();
            targetReferences.add(kind + " " + from + " " + reference.getReferenceType() +
                " " + ownerText);
            if (owner != null) {
                functions.computeIfAbsent(owner.getEntryPoint(), key -> new LinkedHashSet<>())
                    .add(kind + " xref toward " + target + " @ " + hit);
                addDirectCallers(owner, functions, "caller of " + owner.getName());
            }
        }
    }

    private void scanAdrpAddPairs(Map<Long, List<TargetHit>> hitsByPage,
            Map<String, List<String>> references,
            Map<Address, Set<String>> functions) {
        InstructionIterator iterator = currentProgram.getListing().getInstructions(true);
        while (iterator.hasNext() && !monitor.isCancelled()) {
            Instruction adrp = iterator.next();
            if (!"adrp".equalsIgnoreCase(adrp.getMnemonicString())) {
                continue;
            }
            Address page = addressOperand(adrp, 1);
            if (page == null) {
                continue;
            }
            List<TargetHit> pageHits = hitsByPage.get(page.getOffset());
            if (pageHits == null) {
                continue;
            }

            String pageRegister = adrp.getDefaultOperandRepresentation(0).trim();
            Instruction next = currentProgram.getListing().getInstructionAfter(adrp.getAddress());
            for (int distance = 0; next != null && distance < 8; distance++) {
                if ("add".equalsIgnoreCase(next.getMnemonicString()) &&
                        pageRegister.equals(next.getDefaultOperandRepresentation(1).trim())) {
                    Scalar immediate = next.getScalar(2);
                    if (immediate != null) {
                        long resolved = page.getOffset() + immediate.getUnsignedValue();
                        for (TargetHit hit : pageHits) {
                            if (hit.address.getOffset() == resolved) {
                                Function owner = currentProgram.getFunctionManager()
                                    .getFunctionContaining(adrp.getAddress());
                                String ownerText = owner == null ? "<outside function>" :
                                    owner.getName() + " @ " + owner.getEntryPoint();
                                references.get(hit.target).add("adrp+add " + adrp.getAddress() +
                                    " -> " + next.getAddress() + " " + ownerText);
                                if (owner != null) {
                                    functions.computeIfAbsent(owner.getEntryPoint(),
                                        key -> new LinkedHashSet<>()).add(
                                        "ADRP+ADD resolves " + hit.target + " @ " + hit.address);
                                    addDirectCallers(owner, functions,
                                        "caller of " + owner.getName());
                                }
                            }
                        }
                    }
                }
                next = currentProgram.getListing().getInstructionAfter(next.getAddress());
            }
        }
    }

    private Address addressOperand(Instruction instruction, int operandIndex) {
        for (Object object : instruction.getOpObjects(operandIndex)) {
            if (object instanceof Address) {
                return (Address) object;
            }
            if (object instanceof Scalar) {
                return toAddr(((Scalar) object).getUnsignedValue());
            }
        }
        return null;
    }

    private void addKnownSeed(long offset, String reason,
            Map<Address, Set<String>> functions) {
        Function function = currentProgram.getFunctionManager().getFunctionAt(toAddr(offset));
        if (function == null) {
            function = currentProgram.getFunctionManager().getFunctionContaining(toAddr(offset));
        }
        if (function != null) {
            functions.computeIfAbsent(function.getEntryPoint(), key -> new LinkedHashSet<>())
                .add(reason);
            addDirectCallers(function, functions, "caller of " + function.getName());
        }
    }

    private String sanitize(String value) {
        if (value == null) {
            return "unknown error";
        }
        return value.replace("*/", "* /").replace('\n', ' ').replace('\r', ' ');
    }
}
