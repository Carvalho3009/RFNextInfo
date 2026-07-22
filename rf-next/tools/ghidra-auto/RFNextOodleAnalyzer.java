// Focused overnight analysis for RF Online NEXT's bundled Oodle code.
//@category RFNext

import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.SourceType;

public class RFNextOodleAnalyzer extends GhidraScript {
    private static final long OODLE_START = 0x08900000L;
    private static final long OODLE_END = 0x08a00000L;
    private static final long NETWORK_START = 0x07d00000L;
    private static final long NETWORK_END = 0x07e00000L;
    private static final long NETWORK_CODEC_START = 0x08cc0000L;
    private static final long NETWORK_CODEC_END = 0x08d10000L;

    private static final Map<Long, String> SEEDS = new LinkedHashMap<>();
    private static final Set<Long> SKIP_RECURSION = new HashSet<>(Arrays.asList(
        0x0897296cL, // assert/log helper
        0x08972984L, // failure helper
        0x089ba5b8L, // allocator helper
        0x089ba5dcL, // allocation failure
        0x089bea8cL  // memory initialization helper
    ));
    private static final Set<Long> FORCE_STARTS = new HashSet<>(Arrays.asList(
        0x07dad388L, // Incoming follows a noreturn destructor tail that Ghidra may merge
        0x08cceeb4L, // small Encode thunk follows another exported helper
        0x08ccf9a8L  // Decode follows stripped Oodle runtime code
    ));

    static {
        SEEDS.put(0x08970738L, "OodleLZ_Decompress_candidate");
        SEEDS.put(0x08970f30L, "OodleLZ_GetFirstChunkCompressor_candidate");
        SEEDS.put(0x0896f824L, "OodleLZ_DecodeChunkDispatcher_candidate");
        SEEDS.put(0x089bd43cL, "OodleLZ_ParseBlockHeader_candidate");
        SEEDS.put(0x089bfcc4L, "OodleCodec_LZNIB_candidate");
        SEEDS.put(0x08972ab4L, "OodleCodec_LZA_candidate");
        SEEDS.put(0x08995534L, "OodleCodec_BitKnit_candidate");
        SEEDS.put(0x089a83a4L, "OodleCodec_Hydra_candidate");
        SEEDS.put(0x07dab9a8L, "OodleNetworkArchives_candidate");
        SEEDS.put(0x07dac300L, "OodleNetworkHandler_candidate_1");
        SEEDS.put(0x07daca1cL, "OodleNetworkHandler_candidate_2");
        SEEDS.put(0x07dacde4L, "OodleNetworkHandler_candidate_3");
        SEEDS.put(0x07dada58L, "OodleNetworkHandler_candidate_5");
        SEEDS.put(0x07dad388L, "OodleNetwork_Incoming_candidate");
        SEEDS.put(0x07dadb48L, "OodleNetwork_Outgoing_candidate");
        SEEDS.put(0x07dadf3cL, "OodleNetwork_EnsureState_candidate");
        SEEDS.put(0x07dae690L, "OodleNetworkFunction_afterIncoming_candidate_1");
        SEEDS.put(0x07dae784L, "OodleNetworkFunction_afterIncoming_candidate_2");
        SEEDS.put(0x07dae934L, "OodleNetworkFunction_afterIncoming_candidate_3");
        SEEDS.put(0x08cced54L, "OodleNetwork_StateSize_candidate");
        SEEDS.put(0x08cced68L, "OodleNetwork_StateInit_candidate");
        SEEDS.put(0x08cceea8L, "OodleNetwork_SharedSize_candidate");
        SEEDS.put(0x08cceeb4L, "OodleNetwork_Encode_candidate");
        SEEDS.put(0x08ccf9a8L, "OodleNetwork_Decode_candidate");
        SEEDS.put(0x08cd02fcL, "OodleNetwork_DictionaryHelper_candidate");
    }

    private static class Pending {
        final Function function;
        final int depth;
        final String reason;

        Pending(Function function, int depth, String reason) {
            this.function = function;
            this.depth = depth;
            this.reason = reason;
        }
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            throw new IllegalArgumentException(
                "Usage: RFNextOodleAnalyzer.java <report-path> [depth] [max-functions]");
        }

        Path reportPath = Paths.get(args[0]).toAbsolutePath();
        int maxDepth = args.length > 1 ? Integer.parseInt(args[1]) : 4;
        int maxFunctions = args.length > 2 ? Integer.parseInt(args[2]) : 250;
        if (reportPath.getParent() != null) {
            Files.createDirectories(reportPath.getParent());
        }

        FunctionManager functions = currentProgram.getFunctionManager();
        ArrayDeque<Pending> queue = new ArrayDeque<>();
        Set<Address> queued = new HashSet<>();
        Set<Address> visited = new HashSet<>();

        for (Map.Entry<Long, String> seed : SEEDS.entrySet()) {
            Function function = ensureFunction(seed.getKey(), seed.getValue());
            if (function != null && queued.add(function.getEntryPoint())) {
                queue.add(new Pending(function, 0, "seed"));
            }
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        decompiler.setSimplificationStyle("decompile");
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("Decompiler: " + decompiler.getLastMessage());
        }

        int completed = 0;
        try (BufferedWriter out = Files.newBufferedWriter(
                reportPath, StandardCharsets.UTF_8)) {
            writeHeader(out, maxDepth, maxFunctions);

            while (!queue.isEmpty() && completed < maxFunctions && !monitor.isCancelled()) {
                Pending pending = queue.removeFirst();
                Function function = functions.getFunctionAt(pending.function.getEntryPoint());
                if (function == null || !visited.add(function.getEntryPoint())) {
                    continue;
                }

                completed++;
                monitor.setMessage("RFNext Oodle " + completed + "/" + maxFunctions +
                    ": " + function.getName());
                println("[" + completed + "] " + function.getName() + " @ " +
                    function.getEntryPoint());

                out.write("\n## " + function.getName() + " @ `" +
                    function.getEntryPoint() + "`\n\n");
                out.write("Depth: " + pending.depth + "; discovered by: " +
                    pending.reason + "\n\n");

                InstructionIterator instructions = currentProgram.getListing()
                    .getInstructions(function.getBody(), true);
                out.write("### Calls\n\n");
                while (instructions.hasNext()) {
                    Instruction instruction = instructions.next();
                    if ("blr".equalsIgnoreCase(instruction.getMnemonicString())) {
                        out.write("- `" + instruction.getAddress() +
                            "` -> indirect `blr`\n");
                    }
                    if (!instruction.getFlowType().isCall()) {
                        continue;
                    }
                    for (Address target : instruction.getFlows()) {
                        Function called = functions.getFunctionAt(target);
                        if (called == null && inRelevantRange(target)) {
                            called = ensureFunction(target.getOffset(), null);
                        }
                        String calledName = called == null ? "<unknown>" : called.getName();
                        out.write("- `" + instruction.getAddress() + "` -> `" +
                            target + "` " + calledName + "\n");

                        if (called != null && pending.depth < maxDepth &&
                                inRelevantRange(called.getEntryPoint()) &&
                                !SKIP_RECURSION.contains(called.getEntryPoint().getOffset()) &&
                                !visited.contains(called.getEntryPoint()) &&
                                queued.add(called.getEntryPoint())) {
                            queue.addLast(new Pending(called, pending.depth + 1,
                                function.getName() + " @ " + instruction.getAddress()));
                        }
                    }
                }

                out.write("\n### Decompiled C\n\n```c\n");
                DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
                if (result.decompileCompleted() && result.getDecompiledFunction() != null) {
                    out.write(result.getDecompiledFunction().getC());
                }
                else {
                    out.write("/* DECOMPILE FAILED: " + sanitize(result.getErrorMessage()) + " */\n");
                }
                out.write("\n```\n");
                out.flush(); // keep a useful partial report if a later function fails
            }

            out.write("\n## Run summary\n\n");
            out.write("- Decompiled functions: " + completed + "\n");
            out.write("- Remaining queued functions: " + queue.size() + "\n");
            out.write("- Cancelled: " + monitor.isCancelled() + "\n");
        }
        finally {
            decompiler.dispose();
        }

        println("Report written to " + reportPath);
    }

    private Function ensureFunction(long offset, String desiredName) throws Exception {
        Address address = toAddr(offset);
        FunctionManager functions = currentProgram.getFunctionManager();
        Function function = functions.getFunctionAt(address);
        if (function == null) {
            Function containing = functions.getFunctionContaining(address);
            if (containing != null) {
                if (FORCE_STARTS.contains(offset)) {
                    functions.removeFunction(containing.getEntryPoint());
                }
                else {
                    return containing;
                }
            }
            if (getInstructionAt(address) == null) {
                disassemble(address);
            }
            function = createFunction(address, null);
        }
        if (function != null && desiredName != null &&
                !desiredName.equals(function.getName()) &&
                (function.getName().startsWith("FUN_") ||
                 function.getName().contains("_candidate"))) {
            function.setName(desiredName, SourceType.USER_DEFINED);
        }
        return function;
    }

    private boolean inRelevantRange(Address address) {
        long value = address.getOffset();
        return (value >= OODLE_START && value < OODLE_END) ||
            (value >= NETWORK_START && value < NETWORK_END) ||
            (value >= NETWORK_CODEC_START && value < NETWORK_CODEC_END);
    }

    private void writeHeader(BufferedWriter out, int maxDepth, int maxFunctions)
            throws Exception {
        out.write("# RF Online NEXT - focused Oodle analysis\n\n");
        out.write("Generated: " + Instant.now() + "\n\n");
        out.write("- Program: `" + currentProgram.getName() + "`\n");
        out.write("- Image base: `" + currentProgram.getImageBase() + "`\n");
        out.write("- Language: `" + currentProgram.getLanguageID() + "`\n");
        out.write("- Recursion depth: " + maxDepth + "\n");
        out.write("- Function limit: " + maxFunctions + "\n\n");
        out.write("Known codec IDs from the binary: 2=LZNIB, 6=LZA, " +
            "10=BitKnit, 12=Hydra. Other codecs may use indirect dispatch.\n");
        out.write("Network seeds were recovered from ARM64 references to " +
            "OodleNetworkHandlerComponent.cpp and OodleNetworkArchives.cpp.\n");
    }

    private String sanitize(String value) {
        if (value == null) {
            return "unknown error";
        }
        return value.replace("*/", "* /").replace('\n', ' ').replace('\r', ' ');
    }
}
