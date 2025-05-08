#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

// Função de pânico original
void atom_panic_bounds_check(uint64_t index, uint64_t length) { // Use uint64_t para usize
    fprintf(stderr, "\n------------------------------------------------\n");
    fprintf(stderr, "ATOM PANIC: Index out of bounds!\n");
    fprintf(stderr, "  Index:  %llu\n", (unsigned long long)index);
    fprintf(stderr, "  Length: %llu\n", (unsigned long long)length);
    fprintf(stderr, "------------------------------------------------\n");
    fflush(stderr);
    abort();
}

// Nova função helper para o check
void atom_do_bounds_check(uint64_t index, uint64_t length) {
    //fprintf(stderr, "Checking bounds: index=%llu, length=%llu\n", (unsigned long long)index, (unsigned long long)length); // Debug opcional
    if (index >= length) {
        atom_panic_bounds_check(index, length);
        // atom_panic_bounds_check chama abort(), então não precisamos de mais nada aqui
    }
    // Se estiver dentro dos limites, a função simplesmente retorna
}
