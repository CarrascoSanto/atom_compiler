# Atom Language - Core (`no_stdlib`) - Documentation (v0.2 - Complete / v0.3 - Planned)

**Status v0.2 (Complete and Operational):** Functional milestone achieved! Parsing, semantic analysis, and LLVM IR code generation work for the language core. Generated LLVM IR for representative examples is compilable (`clang -fPIE` or `llc -relocation-model=pic`) and executes core logic correctly.

*   **Implemented and Verified Features (Semantic Analysis and CodeGen):**
    *   Definition and usage of `struct` (including literals).
    *   Arrays: types `[T; N]`, literals (`[]`, `[val; N]`).
    *   Slices: types `&[T]`, `&mut [T]`, initialization (e.g., `&[]`), coercion from `&array` to slice, length access (`.len`), element access (`[index]` for read/write).
    *   **Bounds Checking:** Runtime bounds checking implemented for array/slice index access (requires `runtime.c` with `atom_do_bounds_check`). Raw pointer access (`*ptr`) is unchecked.
    *   FFI: Calls to external C functions, including functions with `...` (varargs).
    *   Control Flow: `if`/`else`, `while`, `loop`, `break`, `continue`.
    *   Variables: `let` (immutable) and `mut` (mutable).
    *   Global Constants (`const`): Scalars and structs.
    *   Operators:
        *   Arithmetic: `+`, `-`, `*`, `/`, `%`.
        *   Comparison: `==`, `!=`, `<`, `>`, `<=`, `>=`.
        *   Logical: `&&`, `||`, `!`.
        *   Bitwise: `&`, `|`, `^`, `~`, `<<`, `>>`.
        *   Cast (`as`): Numeric, pointer-to-pointer, integer-to-pointer, pointer-to-integer, bool-to-integer, enum-to-integer, `u8`-to-`char`.
        *   Address and Dereference: `&`, `&mut`, `*`.
    *   `mem` blocks (for unsafe context).
    *   Function Pointers: Type definition (`func(...) -> RetType`), assignment, and call via variable.
    *   C-Like Enums: Definition, variant access (`::`), usage in variables and comparisons (mapped to `i32`).
    *   `byte string` literals (`b"..."`): Creation and assignment to `&[u8]` variables.
    *   **Internal Fixes:** Resolved CFG generation issues for loops/ifs, function identifier handling, and `icmp` instruction generation.
*   **Possible Refinements/Improvements (v0.2):**
    *   **(Technical/Minor):** Investigate `llvmlite.binding.TargetData` API for robust pointer size detection and eliminate `__init__` warnings (current 64-bit fallback works). Consider removing `get_abi_size` fallback code.
    *   **(Quality):** Code cleanup (remove debug prints, add comments/docstrings).
    *   **(Grammar/Minor):** Resolve LALR `if/else` ambiguity (optional, Earley works).
*   **Current Limitations:**
    *   Warning about pointer size detection in `__init__` remains (functional fallback).
    *   Dependency on `runtime.c` for bounds checking.
*   **Grammar:** Minor LALR conflict in `if/else` (Earley fallback works).

**Status v0.3 (Planned):** Introduction of **Bidirectional Type Inference** (focus on generics), simplified Borrow Checking, **Native Print** (alternative to FFI), low-level I/O primitives, potential `match` and enums with data, **Literal Suffixes** (e.g., `100_u16`), exploration of **Coroutines** (with Lua-like semantics for simple cooperative concurrency), string concatenation (+), and native Bounds Checking (without `runtime.c`).

**Version History:**
*   v0.1: Minimal focus for "Hello, World!" via FFI.
*   **v0.2 (Complete):** Functional `no_stdlib` base established, robust semantic analysis, functional LLVM CodeGen (including slice `.len` and `[index]`).
*   v0.3 (Planned): Bidirectional Inference, Borrow Checker (simplified), **Native Print**, I/O, `match`, Enums with data, Literal Suffixes, **Coroutines (Lua-style)**, string concatenation (+), native Bounds Checking.

## 1. Philosophy (Core v0.2 / v0.3)

*   **Controlled Minimalism:** Essential `no_std` features, focus on integer/pointer types.
*   **Readability:** Clean syntax, use of `end`, comments (`#`, `//`).
*   **Progressive Safety:** Mutability checks (`let`/`mut`) [v0.2]. Borrow checking (simplified) [v0.3].
*   **Explicit Portal (`mem`):** `mem ... end` block for unsafe operations (deref `*`, ptr/int casts, FFI [v0.2]). Semantic verification of necessity [Post-v0.2].
*   **Explicit Control:** Strong static typing, preferential annotations. Function pointers [v0.2]. Bitwise operators [v0.2].
*   **Optional Convenience:** Simple local type inference (int literals inferred as `i32`) [v0.2]. **Bidirectional Inference** [v0.3]. **Native Print** [v0.3].
*   **Native Compilation:** Generates optimizable LLVM IR [v0.2].
*   **Focus on Low-Level and Embedded:** Fixed-size types, explicit control. No GC.
*   **Foundation for SDK/Specific Libs:** `no_stdlib` core.

## 2. Lexical Structure (Core v0.2 - Complete)

*   **Comments:** `#` (single-line), `//` (single-line), `"""..."""` (multi-line/docstring).
*   **Reserved Keywords:**
    *   Structure/Declaration: `func`, `struct`, `enum`, `const`, `import`, `extern`, `mem`, `let`, `mut`.
    *   Control Flow: `if`, `else`, `loop`, `while`, `break`, `continue`, `return`.
    *   **Blocks:** `end`.
    *   Primitive Types: `int`, `uint`, `iN`, `uN`, `bool`, `char`, `usize`, `isize`.
    *   Values: `true`, `false`.
    *   Operators/Others: `as`.
*   **Identifiers:** `[a-zA-Z_][a-zA-Z0-9_]*`.
*   **Literals:** Integers (dec/hex/oct/bin with `_`), Booleans, Strings (`""`), Byte Strings (`b""`), Characters (`''`), Arrays (`[]`, `[val; N]`), Structs (`Name { ... }`).
*   **Operators:** `=`, `()`, `->`, `:`, `*`, `&` (address/bitwise AND), `&mut`, `.`, `::`, `[]`, `==`, `!=`, `<`, `>`, `<=`, `>=`, `&&`, `||`, `!`, `+`, `-`, `/`, `%`, `|` (bitwise OR), `^` (bitwise XOR), `~` (bitwise NOT), `<<` (shift left), `>>` (shift right), `as`.
*   **Delimiters:** `( )`, `[ ]`, `{ }` (only for struct literals), `;`, `,`, `...` (varargs).

## 3. Types (Core v0.2 - Complete)

*   **Primitive Integers:** `int`, `uint`, `i8`-`i64`, `u8`-`u64`, `usize`, `isize`.
*   **Other Primitives:** `bool`, `char`.
*   **Unit Type:** `()`.
*   **Reference and Pointer Types:** `&T`, `&mut T`, `*const T`, `*mut T`.
*   **Composite Types:** `struct Name ... end`, `enum Name ... end` (C-Like, mapped to `i32` in LLVM).
*   **Collection Types:** `[T; N]` (array), `&[T]`, `&mut [T]` (slices).
*   **Integer Literal Types:** Default inference to `i32`; compatibility checked against expected type.
*   **Function Pointer Type:** `func(T1, T2) -> RetType`.

## 4. Features (Core v0.2 - Complete)

*   **Function Definition:** OK.
*   **Variables (`let`/`mut`):** OK.
*   **Ownership/Borrowing:** Syntax OK. Checker [v0.3].
*   **`mem` Block:** Syntax OK. Semantic verification of necessity [Post-v0.2].
*   **FFI (Foreign Function Interface):** OK (including varargs).
*   **Literals:**
    *   Integers (including bases, `_`): Parsing, analysis, and LLVM CodeGen OK.
    *   Strings (`""`): Parsing, analysis (escapes OK), and LLVM CodeGen (as global `i8*`) OK.
    *   Booleans (`true`, `false`): Parsing, analysis, and LLVM CodeGen (as `i1`) OK.
    *   Characters (`''`): Parsing, analysis (escapes OK), and LLVM CodeGen (as `i8`) OK.
    *   Byte Strings (`b""`): Parsing, analysis, and LLVM CodeGen (as global `[N x i8]` and slice value `{i8*, usize}`) OK.
    *   Arrays (`[]`, `[val; N]`): Parsing, analysis, and LLVM CodeGen OK.
    *   Structs (`Name{...}`): Parsing, analysis, and LLVM CodeGen OK.
*   **Access:**
    *   `.field` (structs): OK.
    *   `.len` (slices): OK.
    *   `[index]` (arrays/slices, read/write): OK.
    *   `::` (C-like enums): Parsing, analysis, and LLVM CodeGen (as integer value) OK.
*   **Operators:**
    *   Arithmetic (`+`, `-`, `*`, `/`, `%`): OK.
    *   Comparison (`==`, `!=`, `<`, `>`, `<=`, `>=`): OK.
    *   Logical (`&&`, `||`, `!`): OK.
    *   Bitwise (`&`, `|`, `^`, `~`, `<<`, `>>`): OK.
    *   Cast (`as`): Numeric, pointer-pointer, int-pointer, pointer-int, bool-int, enum-int, u8-char OK.
    *   Address/Dereference (`&`, `&mut`, `*`): OK.
*   **Control Flow:**
    *   `if`/`else`: Parsing, analysis, and LLVM CodeGen OK.
    *   `while`: Parsing, analysis, and LLVM CodeGen OK.
    *   `loop`, `break`, `continue`: Parsing, analysis, and LLVM CodeGen OK.
*   **`return`:** OK.
*   **Constants (`const`):**
    *   Scalars: Parsing, analysis, and LLVM CodeGen OK.
    *   Structs: Parsing, analysis, and LLVM CodeGen OK.
    *   Full constancy verification (constexpr) [Post-v0.2].
*   **`import`:** Syntax OK, non-functional.
*   **Function Pointers:** Type definition, semantic analysis, assignment, call via variable, LLVM CodeGen OK.
*   **C-Like Enums:** Definition, semantic analysis, variant access (`::`), and LLVM CodeGen (as `i32`) OK.

## 5. Missing Features / Main TODOs (Post-v0.2)

*   **Core v0.2 - Minor Refinements (Optional):**
    *   **(Technical):** Investigate `TargetData` API for robust pointer size detection and eliminate `__init__` warnings.
    *   **(Safety):** Implement bounds checking for array/slice index access (`[index]`).
    *   **(Optimization):** Refine logic in `visit_IfStmt` to avoid placing builder in dead `merge` blocks (LLVM optimizes, low priority).
    *   **(Quality):** Code cleanup (remove debug prints, add comments).
    *   **(Grammar):** Resolve LALR `if/else` ambiguity (optional, Earley works).
    *   **(Semantics):** Implement necessity verification for `mem` blocks.
    *   **(Semantics):** Implement robust constancy checks for `const` expressions (`is_constant_expression`).
*   **Next Version (v0.3 - Planned):**
    *   **Bidirectional Type Inference.**
    *   **Borrow Checker (Simplified).**
    *   **Native Print (Macros? Intrinsics?).**
    *   **Primitive I/O.**
    *   **`match`.**
    *   **Enums with Data.**
    *   **Literal Suffixes** (e.g., `100_u16`).
    *   **Coroutines (Lua-style).**

## 6. Revised Example (v0.2 - Complete with Working Slices)

```atom
# Struct definition with 'end'
struct Vec2
    x: i32,
    y: i32,
end

struct MyData
    id: i32,
end

# Function using slices
func process_slice(data_slice: &[MyData], empty_slice: &[i32]) -> usize
    let len1 = data_slice.len; # OK
    let len2 = empty_slice.len; # OK (Should be 0)

    if len1 > (0 as usize)
        let first_id = data_slice[0].id; # OK: Index and field access
        mem printf("First ID: %d\n", first_id); end
    end 
    return len1 + len2;
end

const SIZE: usize = 5;
const ORIGIN: Vec2 = Vec2 { x: 0, y: 0 };

# Extern block with 'end'
extern "C"
    func printf(*const char, ...) -> i32; 
    func puts(*const char) -> i32;
end

struct Entity
    pos: &mut Vec2,
    vel: Vec2,
    tag: *const char,
    sprite_ids: [u8; 4],
    neighbors: &[Entity],
end

# Enum with 'end'
enum State
    Idle, Running, Jumping,
end

# Callback test function
func my_callback_func(n: i32) -> bool
    if n > 0
        return true;
    else
        return false;
    end
end

# Function definition with 'end'
func update_entity(e: &mut Entity, dt_scale_factor: i32) -> ()
    let move_x = (e.vel.x * dt_scale_factor) / (256 as i32);
    let _ = e.pos.x; 
    return;
end 

func main() -> ()
    let score: i32 = (100 * 2 + 50) as i32;
    mut current_pos = Vec2 { x: 10, y: 20 };
    let static_msg: *const char = "Hello Atom!";
    let another_msg: *const char = "A simple line.";

    let points: [Vec2; 3] = [ Vec2{x:1, y:1}, ORIGIN, Vec2{x: -1, y:-1}, ];
    let empty_entities: &[Entity] = &[];
    let default_sprites: [u8; 4] = [1 as u8; 4];

    let next_score = score / (2 as i32);
    let is_zero = current_pos.x == ORIGIN.x && current_pos.y == ORIGIN.y;
    let first_pt_x = points[0].x;

    mem
         let temp_ptr = another_msg; 
         puts(temp_ptr);             
         printf("Hello %d\n", 123);    
    end 

    mut player_entity = Entity {
        pos: &mut current_pos,       
        vel: Vec2 { x: (5 * 256) as i32, y: 0 },
        tag: static_msg,              
        sprite_ids: default_sprites, 
        neighbors: empty_entities,   
    };

    if is_zero || first_pt_x < (0 as i32)
        mem end
    else
        mut i: i32 = 0;
        while i < (3 as i32)
             let dummy = i + (1 as i32);
             i = dummy; 
        end 
    end 

    mem end

    let flags: u8 = 0b1100_1010;
    let masked = flags & 0b0000_1111;
    let shifted = masked << 2;
    let inverted = ~flags;
    let combined = shifted | 1;
    let xor_test = combined ^ masked;

    let cb: func(i32)->bool = my_callback_func; 
    let is_pos = cb(10);                         
    let is_neg = cb(-5);
    
    let current_state: State = State::Running;
    let next_state: State = State::Idle;

    mem
        printf("Current state: %d, Next state: %d\n", 
            current_state as u32, 
            next_state as u32);
    end

    if current_state == State::Running
        mem printf("Entity is running!\n"); end 
    end
    
    let my_bstr: &[u8] = b"Atom\x01\x02\x03"; 
    
    mut k: i32 = 0;
    loop
        k = k + 1;
        if k == 2
            continue;
        end
        mem printf("Loop k: %d\n", k as u32); end 
        if k == 4
            break;
        end
    end
    mem printf("Loop finished with k: %d\n", k as u32); end 

    mut j: i32 = 0;
    while j < 5
        j = j + 1;
        if j == 3
            mem printf("While j==3, continue\n"); end 
            continue;
        end
        if j == 5
            mem printf("While j==5, break\n"); end 
            break;
        end
        mem printf("While j: %d\n", j as u32); end 
    end
    mem printf("While finished with j: %d\n", j as u32); end 

    mem
        printf("Masked: %u, Shifted: %u, Combined: %u, Inverted: %u, XOR: %u\n", 
               masked as u32, shifted as u32, combined as u32, inverted as u32, xor_test as u32);
    end

    mem
        printf("Callback results: %u, %u\n", is_pos as u32, is_neg as u32); 
    end
    
    let d1 = MyData { id: 10 };
    let d2 = MyData { id: 20 };
    let d3 = MyData { id: 30 };

    let my_array: [MyData; 3] = [d1, d2, d3];
    let a_slice: &[MyData] = &my_array;      
    let another_slice: &[MyData] = a_slice;  
    let empty: &[i32] = &[];               

    let res = process_slice(another_slice, empty);
    mem printf("Total len from process_slice: %lu\n", res as u64); end

    mut mut_array: [i32; 2] = [100, 200];
    let mut_s: &mut [i32] = &mut mut_array;
    
    if mut_s.len > (1 as usize)
        mut_s[1] = mut_s[0] + 50; 
        mem printf("mut_s[1] is now: %d\n", mut_s[1]); end
    end 
    
    let b_str_slice: &[u8] = b"hello";
    if b_str_slice.len > (0 as usize)
        mem printf("First char of b_str_slice: %c\n", b_str_slice[0] as char); end
    end 

    let my_bytes_test: &[u8] = b"Data"; 

    return;
end
