# ast_nodes.py (CORRIGIDO para usar @dataclass consistentemente)
"""
Módulo da Árvore Sintática Abstrata (AST) para Atom Core v0.2.
Define as classes Python que representam cada construção sintática
da linguagem Atom v0.2.
"""

from typing import List, Union, Optional, Any
from dataclasses import dataclass, field

# --- Classes Base ---

@dataclass
class Node:
    """Classe base para todos os nós da AST."""
    # O dataclass gera __init__, __repr__, __eq__ etc. automaticamente
    pass

@dataclass
class Statement(Node):
    """Classe base para nós que representam comandos ou declarações."""
    pass

@dataclass
class Expression(Node):
    """Classe base para nós que representam expressões."""
    pass

@dataclass
class Type(Node):
    """Classe base para nós que representam tipos da linguagem."""
    pass

# --- Nós de Tipo Específicos (v0.2) ---

@dataclass
class PrimitiveType(Type):
    """Representa um tipo primitivo nomeado (ex: 'int', 'u8', 'bool')."""
    name: str
    # __init__ e __repr__ gerados automaticamente

@dataclass
class PointerType(Type):
    """Representa um tipo ponteiro bruto (ex: '*const u8', '*mut i32')."""
    pointee_type: Type # O tipo para o qual aponta
    is_mutable: bool   # True para *mut, False para *const

    # __repr__ customizado para melhor legibilidade
    def __repr__(self):
        mod = "mut" if self.is_mutable else "const"
        return f"PointerType(modifier='{mod}', pointee={self.pointee_type!r})"

@dataclass
class ReferenceType(Type):
    """Representa um tipo referência segura (borrow) (ex: '&T', '&mut T')."""
    referenced_type: Type # O tipo referenciado
    is_mutable: bool      # True para &mut, False para &

    # __repr__ customizado
    def __repr__(self):
        mod = "&mut" if self.is_mutable else "&"
        return f"ReferenceType(modifier='{mod}', referenced={self.referenced_type!r})"

@dataclass
class ArrayType(Type):
    """Representa um tipo array de tamanho fixo (ex: '[u8; 1024]')."""
    element_type: Type
    size: Expression # Tamanho deve ser expressão constante (verificado semanticamente)
    # __init__ e __repr__ gerados automaticamente

@dataclass
class SliceType(Type):
    """Representa um tipo slice (view) (ex: '&[u8]', '&mut [i32]')."""
    element_type: Type
    is_mutable: bool # True para &mut, False para &

    # __repr__ customizado
    def __repr__(self):
        mod = "&mut" if self.is_mutable else "&"
        return f"SliceType(modifier='{mod}', element={self.element_type!r})"

@dataclass
class UnitType(Type):
    """Representa o tipo 'Unit' (vazio), denotado por '()'. """
    pass # Não precisa de campos. __init__ e __repr__ gerados.

@dataclass
class CustomType(Type):
    """Representa um tipo definido pelo usuário (struct/enum) referenciado por nome."""
    name: 'Identifier' # Nome do tipo (precisa ser resolvido semanticamente)
    # __init__ e __repr__ gerados automaticamente

@dataclass
class LiteralIntegerType(Type):
    """Tipo intermediário para literais inteiros, usado na análise semântica."""
    value: int
    default_type_name: str # 'i32' ou 'u32'

    # __repr__ customizado
    def __repr__(self) -> str:
        return f"LiteralInteger({self.value}:{self.default_type_name})"

# --- Nós de Expressão Específicos (v0.2) ---

@dataclass
class Identifier(Expression):
    """Representa um identificador."""
    name: str
    # __init__ e __repr__ gerados automaticamente

@dataclass
class Literal(Expression):
    """Classe base abstrata para literais."""
    # Nota: Fazer Literal ser @dataclass pode exigir que subclasses definam 'value'
    value: Any

@dataclass
class IntegerLiteral(Literal):
    """Representa um literal inteiro."""
    # 'value' é herdado e __init__ gerado. Sobrescreve __repr__ se necessário.
    value: int # Especifica o tipo para o dataclass
    # __repr__ gerado é bom: IntegerLiteral(value=123)

@dataclass
class StringLiteral(Literal):
    """Representa um literal de string."""
    value: str # Espera string Python já processada
    # __repr__ gerado: StringLiteral(value='hello')

@dataclass
class ByteStringLiteral(Literal):
     """Representa um literal de byte string."""
     value: bytes # Espera objeto bytes Python
     # __repr__ gerado: ByteStringLiteral(value=b'data')

@dataclass
class BooleanLiteral(Literal):
    """Representa um literal booleano."""
    value: bool
    # __repr__ gerado: BooleanLiteral(value=True)

@dataclass
class CharLiteral(Literal):
     """Representa um literal de caractere."""
     value: str # Espera string Python de tamanho 1
     # __repr__ gerado: CharLiteral(value='a')

@dataclass
class ArrayLiteral(Expression):
    """Representa um literal de array (ex: '[1, 2, 3]')."""
    elements: List[Expression] # Lista de nós de expressão para os elementos
    # __init__ e __repr__ gerados automaticamente

@dataclass
class StructLiteralField(Node): # Não é Expression nem Statement por si só
    """Representa um campo individual em um struct literal (ex: 'x: 10')."""
    name: Identifier # Nome do campo
    value: Expression # Expressão do valor do campo
    # __init__ e __repr__ gerados automaticamente

@dataclass
class StructLiteral(Expression):
    """Representa um literal de struct (ex: 'Point { x: 10, y: 20 }')."""
    type_name: Identifier # Nome do struct sendo instanciado
    fields: List[StructLiteralField] # Lista dos campos inicializados
    # __init__ e __repr__ gerados automaticamente

@dataclass
class FunctionCall(Expression):
    """Representa uma chamada de função."""
    callee: Expression # Expressão que resulta na função a ser chamada
    args: List[Expression] # Lista de expressões dos argumentos
    # __init__ e __repr__ gerados automaticamente

@dataclass
class BinaryOp(Expression):
    """Representa uma operação binária."""
    op: str # O operador como string (ex: "+", "==")
    left: Expression
    right: Expression
    # __init__ e __repr__ gerados automaticamente

@dataclass
class UnaryOp(Expression):
    """Representa uma operação unária prefixa."""
    op: str # O operador como string (ex: "!", "-", "*", "&", "&mut")
    operand: Expression
    # __init__ e __repr__ gerados automaticamente

@dataclass
class FieldAccess(Expression):
    """Representa acesso a campo de struct (ex: 'player.pos')."""
    obj: Expression # A expressão que resulta no struct
    field: Identifier # O identificador do campo acessado
    # __init__ e __repr__ gerados automaticamente

@dataclass
class IndexAccess(Expression):
    """Representa acesso a índice de array/slice (ex: 'buffer[i]')."""
    array: Expression # A expressão que resulta no array/slice
    index: Expression # A expressão que calcula o índice
    # __init__ e __repr__ gerados automaticamente

@dataclass
class CastExpr(Expression):
    """Representa uma expressão de cast (ex: 'val as u32')."""
    expr: Expression # A expressão sendo convertida
    target_type: Type # O tipo para o qual converter
    # __init__ e __repr__ gerados automaticamente

# GroupedExpr não é necessário se o parser lida com precedência e o transformer
# extrai a expressão interna diretamente.

@dataclass
class Underscore(Expression):
    """Representa o underscore '_' usado como expressão/placeholder."""
    # Geralmente não tem valor, mas pode ter metadados no futuro.
    pass # __init__ e __repr__ gerados

@dataclass
class ArrayRepeatExpr(Expression):
    """Representa uma expressão de inicialização de array: [valor; tamanho]"""
    value: Expression  # O valor a ser repetido
    size: Expression   # A expressão que define o tamanho
    # __init__ e __repr__ gerados automaticamente

@dataclass
class NamespaceAccess(Expression):
    """Representa acesso a um item dentro de um namespace/enum (ex: Color::Red)."""
    namespace: Identifier # O nome do namespace/enum/módulo
    item: Identifier # O nome do item
    # __init__ e __repr__ gerados automaticamente

# --- Nós de Declaração/Comando Específicos (v0.2) ---

@dataclass
class Parameter(Node):
    """Representa um parâmetro na definição de uma função (nome: tipo)."""
    name: Identifier
    type: Type
    # __init__ e __repr__ gerados automaticamente

@dataclass
class LetBinding(Statement):
    """Representa uma declaração 'let' (vinculação imutável)."""
    name: Identifier
    type_annot: Optional[Type] # Anotação de tipo (pode ser None)
    value: Expression # Expressão de inicialização
    # __init__ e __repr__ gerados automaticamente

@dataclass
class MutBinding(Statement):
    """Representa uma declaração 'mut' (vinculação mutável)."""
    name: Identifier
    type_annot: Optional[Type]
    value: Expression
    # __init__ e __repr__ gerados automaticamente

@dataclass
class Assignment(Statement):
    """Representa uma atribuição a um L-Value."""
    target: Expression # Alvo (Identifier, FieldAccess, IndexAccess, Underscore)
    value: Expression  # Valor a ser atribuído
    # __init__ e __repr__ gerados automaticamente

@dataclass
class MemBlock(Statement):
    """Representa um bloco 'mem { ... }'."""
    body: List[Statement] # Lista de statements dentro do bloco
    # __init__ e __repr__ gerados automaticamente
    
@dataclass
class EMemBlock(Statement): # <--- NOVA CLASSE
    """Representa um bloco 'e_mem { ... } end' que cria um novo escopo."""
    body: List[Statement]
    # __init__ e __repr__ gerados automaticamente

@dataclass
class IfStmt(Statement):
    """Representa uma declaração condicional 'if'/'else if'/'else'."""
    condition: Expression
    then_block: List[Statement]
    # else_block pode ser None, List[Statement] (bloco else), ou IfStmt (else if)
    else_block: Optional[Union['IfStmt', List[Statement]]]
    # __init__ e __repr__ gerados automaticamente

@dataclass
class LoopStmt(Statement):
    """Representa um loop infinito 'loop { ... }'."""
    body: List[Statement]
    # __init__ e __repr__ gerados automaticamente

@dataclass
class WhileStmt(Statement):
    """Representa um loop condicional 'while condition { ... }'."""
    condition: Expression
    body: List[Statement]
    # __init__ e __repr__ gerados automaticamente

@dataclass
class BreakStmt(Statement):
    """Representa o comando 'break'."""
    pass # __init__ e __repr__ gerados

@dataclass
class ContinueStmt(Statement):
    """Representa o comando 'continue'."""
    pass # __init__ e __repr__ gerados

@dataclass
class ReturnStmt(Statement):
    """Representa o comando 'return [expression]'."""
    value: Optional[Expression] # A expressão retornada (ou None)
    # __init__ e __repr__ gerados automaticamente

@dataclass
class ExpressionStatement(Statement):
    """Representa uma expressão usada como uma instrução (terminada por ';')."""
    expression: Expression
    # __init__ e __repr__ gerados automaticamente


# --- Nós de Definição/Declaração de Top-Level (v0.2) ---

@dataclass
class FunctionDecl(Node):
    """Representa a declaração de uma função externa."""
    name: Identifier
    params: List[Parameter]
    return_type: Type
    is_var_arg: bool = False # NOVO CAMPO, padrão False
    # __init__ gerado automaticamente

    # Opcional: Atualizar __repr__
    def __repr__(self):
         return f"FunctionDecl(name={self.name!r}, params={self.params!r}, return_type={self.return_type!r}, vararg={self.is_var_arg})"

@dataclass
class ExternBlock(Node):
    """Representa um bloco 'extern "ABI" { ... }'."""
    abi: StringLiteral # A ABI como um literal de string
    declarations: List[FunctionDecl]
    # __init__ e __repr__ gerados automaticamente
    
@dataclass
class FunctionType(Type):
    """Representa um tipo ponteiro para função (ex: func(i32) -> bool)."""
    param_types: List[Type] # Lista dos tipos dos parâmetros
    return_type: Type      # O tipo de retorno
    is_var_arg: bool = False # <<< ADICIONAR ESTE CAMPO (com default False)

    # __repr__ customizado para legibilidade
    def __repr__(self):
        params_str = ", ".join(repr(p) for p in self.param_types)
        vararg_str = ", ..." if self.is_var_arg else "" # <<< Atualiza repr
        return f"FunctionType(params=[{params_str}{vararg_str}], return={self.return_type!r})"
        
@dataclass
class FunctionDef(Node):
    """Representa a definição de uma função completa."""
    name: Identifier
    params: List[Parameter]
    return_type: Type
    body: List[Statement] # Lista de statements do corpo
    # __init__ e __repr__ gerados automaticamente

@dataclass
class StructFieldDef(Node):
    """Representa a definição de um campo dentro de um 'struct'."""
    name: Identifier
    type: Type
    # __init__ e __repr__ gerados automaticamente

@dataclass
class StructDef(Node):
    """Representa a definição de um struct."""
    name: Identifier
    fields: List[StructFieldDef]
    # __init__ e __repr__ gerados automaticamente

@dataclass
class EnumVariantDef(Node):
    """Representa a definição de uma variante dentro de um 'enum'."""
    name: Identifier
    # __init__ e __repr__ gerados automaticamente

@dataclass
class EnumDef(Node):
    """Representa a definição de um enum."""
    name: Identifier
    variants: List[EnumVariantDef]
    # __init__ e __repr__ gerados automaticamente

@dataclass
class ConstDef(Node):
    """Representa a definição de uma constante."""
    name: Identifier
    type_annot: Type
    value: Expression # Deve ser avaliável em tempo de compilação
    # __init__ e __repr__ gerados automaticamente

@dataclass
class ImportDecl(Node):
    """Representa uma declaração de importação."""
    path: StringLiteral # O caminho como um StringLiteral
    # __init__ e __repr__ gerados automaticamente

@dataclass
class Program(Node):
    """Nó raiz da AST."""
    body: List[Node] # Lista de itens de nível superior
    # __init__ e __repr__ gerados automaticamente

# --- Fim das Definições da AST (v0.2) ---
