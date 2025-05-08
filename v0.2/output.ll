; ModuleID = "atom_module"
target triple = "x86_64-unknown-linux-gnu"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"

%"Vec2" = type {i32, i32}
%"Entity" = type {%"Vec2"*, %"Vec2", i8*, [4 x i8], {%"Entity"*, i64}}
@"SIZE" = internal constant i64 5
@"ORIGIN" = internal constant %"Vec2" zeroinitializer
declare i32 @"printf"()

declare i32 @"puts"(i8* %".1")

define void @"update_entity"(%"Entity"* %"e", i32 %"dt_scale_factor")
{
entry:
  %"e.addr" = alloca %"Entity"*
  store %"Entity"* %"e", %"Entity"** %"e.addr"
  %"dt_scale_factor.addr" = alloca i32
  store i32 %"dt_scale_factor", i32* %"dt_scale_factor.addr"
  %"e.1" = load %"Entity"*, %"Entity"** %"e.addr"
  %"e.loadptr" = load %"Entity"*, %"Entity"** %"e.addr"
  %"vel.ptr" = getelementptr inbounds %"Entity", %"Entity"* %"e.loadptr", i32 0, i32 1
  %"vel.load" = load %"Vec2", %"Vec2"* %"vel.ptr"
  %"x.extract" = extractvalue %"Vec2" %"vel.load", 0
  %"dt_scale_factor.1" = load i32, i32* %"dt_scale_factor.addr"
  %"multmp" = mul i32 %"x.extract", %"dt_scale_factor.1"
  %"sdivtmp" = sdiv i32 %"multmp", 256
  %"move_x.addr" = alloca i32
  store i32 %"sdivtmp", i32* %"move_x.addr"
  %"e.2" = load %"Entity"*, %"Entity"** %"e.addr"
  %"e.loadptr.1" = load %"Entity"*, %"Entity"** %"e.addr"
  %"vel.ptr.1" = getelementptr inbounds %"Entity", %"Entity"* %"e.loadptr.1", i32 0, i32 1
  %"vel.load.1" = load %"Vec2", %"Vec2"* %"vel.ptr.1"
  %"y.extract" = extractvalue %"Vec2" %"vel.load.1", 1
  %"dt_scale_factor.2" = load i32, i32* %"dt_scale_factor.addr"
  %"multmp.1" = mul i32 %"y.extract", %"dt_scale_factor.2"
  %"sdivtmp.1" = sdiv i32 %"multmp.1", 256
  %"move_y.addr" = alloca i32
  store i32 %"sdivtmp.1", i32* %"move_y.addr"
  %"e.3" = load %"Entity"*, %"Entity"** %"e.addr"
  %"e.loadptr.2" = load %"Entity"*, %"Entity"** %"e.addr"
  %"pos.ptr" = getelementptr inbounds %"Entity", %"Entity"* %"e.loadptr.2", i32 0, i32 0
  %"pos.load" = load %"Vec2"*, %"Vec2"** %"pos.ptr"
  %"e.loadptr.3" = load %"Entity"*, %"Entity"** %"e.addr"
  %"pos.ptr.1" = getelementptr inbounds %"Entity", %"Entity"* %"e.loadptr.3", i32 0, i32 0
  %".8" = load %"Vec2"*, %"Vec2"** %"pos.ptr.1"
  %"x.ptr" = getelementptr inbounds %"Vec2", %"Vec2"* %".8", i32 0, i32 0
  %"x.load" = load i32, i32* %"x.ptr"
  %"_.addr" = alloca i32
  store i32 %"x.load", i32* %"_.addr"
  ret void
}

define void @"main"()
{
entry:
  %"multmp" = mul i32 100, 2
  %"addtmp" = add i32 %"multmp", 50
  %"score.addr" = alloca i32
  store i32 %"addtmp", i32* %"score.addr"
  %"x.insert" = insertvalue %"Vec2" zeroinitializer, i32 10, 0
  %"y.insert" = insertvalue %"Vec2" %"x.insert", i32 20, 1
  %"current_pos.addr" = alloca %"Vec2"
  store %"Vec2" %"y.insert", %"Vec2"* %"current_pos.addr"
  %"static_msg.addr" = alloca i8*
  store i8* getelementptr ([12 x i8], [12 x i8]* @".str.lit.0", i32 0, i32 0), i8** %"static_msg.addr"
  %"another_msg.addr" = alloca i8*
  store i8* getelementptr ([19 x i8], [19 x i8]* @".str.lit.1", i32 0, i32 0), i8** %"another_msg.addr"
  %"x.insert.1" = insertvalue %"Vec2" zeroinitializer, i32 1, 0
  %"y.insert.1" = insertvalue %"Vec2" %"x.insert.1", i32 1, 1
  %"negtmp" = sub i32 0, 1
  %"x.insert.2" = insertvalue %"Vec2" zeroinitializer, i32 %"negtmp", 0
  %"negtmp.1" = sub i32 0, 1
  %"y.insert.2" = insertvalue %"Vec2" %"x.insert.2", i32 %"negtmp.1", 1
  %"elem0.insert" = insertvalue [3 x %"Vec2"] zeroinitializer, %"Vec2" %"y.insert.1", 0
  %"elem1.insert" = insertvalue [3 x %"Vec2"] %"elem0.insert", %"Vec2" zeroinitializer, 1
  %"elem2.insert" = insertvalue [3 x %"Vec2"] %"elem1.insert", %"Vec2" %"y.insert.2", 2
  %"points.addr" = alloca [3 x %"Vec2"]
  store [3 x %"Vec2"] %"elem2.insert", [3 x %"Vec2"]* %"points.addr"
  %"empty_entities.addr" = alloca {%"Entity"*, i64}
  store {%"Entity"*, i64} {%"Entity"* null, i64 0}, {%"Entity"*, i64}* %"empty_entities.addr"
  %"trunctmp" = trunc i32 1 to i8
  %"score" = load i32, i32* %"score.addr"
  %"sdivtmp" = sdiv i32 %"score", 2
  %"next_score.addr" = alloca i32
  store i32 %"sdivtmp", i32* %"next_score.addr"
  %"current_pos" = load %"Vec2", %"Vec2"* %"current_pos.addr"
  %"x.extract" = extractvalue %"Vec2" %"current_pos", 0
  %"x.extract.1" = extractvalue %"Vec2" zeroinitializer, 0
  %"cmptmp" = icmp eq i32 %"x.extract", %"x.extract.1"
  %"current_pos.1" = load %"Vec2", %"Vec2"* %"current_pos.addr"
  %"y.extract" = extractvalue %"Vec2" %"current_pos.1", 1
  %"y.extract.1" = extractvalue %"Vec2" zeroinitializer, 1
  %"cmptmp.1" = icmp eq i32 %"y.extract", %"y.extract.1"
  %"current_pos.2" = load %"Vec2", %"Vec2"* %"current_pos.addr"
  %"x.extract.2" = extractvalue %"Vec2" %"current_pos.2", 0
  %"x.extract.3" = extractvalue %"Vec2" zeroinitializer, 0
  %"cmptmp.2" = icmp eq i32 %"x.extract.2", %"x.extract.3"
  br i1 %"cmptmp.2", label %"op.&&.eval_b", label %"op.&&.merge"
"op.&&.eval_b":
  %"current_pos.3" = load %"Vec2", %"Vec2"* %"current_pos.addr"
  %"y.extract.2" = extractvalue %"Vec2" %"current_pos.3", 1
  %"y.extract.3" = extractvalue %"Vec2" zeroinitializer, 1
  %"cmptmp.3" = icmp eq i32 %"y.extract.2", %"y.extract.3"
  br label %"op.&&.merge"
"op.&&.merge":
  %"op.&&.result" = phi  i1 [0, %"entry"], [%"cmptmp.3", %"op.&&.eval_b"]
  %"is_zero.addr" = alloca i1
  store i1 %"op.&&.result", i1* %"is_zero.addr"
  %"idx.sext" = sext i32 0 to i64
  %"arr.elem.ptr" = getelementptr inbounds [3 x %"Vec2"], [3 x %"Vec2"]* %"points.addr", i32 0, i64 %"idx.sext"
  %"idx.load" = load %"Vec2", %"Vec2"* %"arr.elem.ptr"
  %"x.extract.4" = extractvalue %"Vec2" %"idx.load", 0
  %"first_pt_x.addr" = alloca i32
  store i32 %"x.extract.4", i32* %"first_pt_x.addr"
  %"pos.insert" = insertvalue %"Entity" zeroinitializer, %"Vec2"* %"current_pos.addr", 0
  %"multmp.1" = mul i32 5, 256
  %"x.insert.3" = insertvalue %"Vec2" zeroinitializer, i32 %"multmp.1", 0
  %"y.insert.3" = insertvalue %"Vec2" %"x.insert.3", i32 0, 1
  %"vel.insert" = insertvalue %"Entity" %"pos.insert", %"Vec2" %"y.insert.3", 1
  %"static_msg" = load i8*, i8** %"static_msg.addr"
  %"tag.insert" = insertvalue %"Entity" %"vel.insert", i8* %"static_msg", 2
  %"is_zero" = load i1, i1* %"is_zero.addr"
  %"first_pt_x" = load i32, i32* %"first_pt_x.addr"
  %"cmptmp.4" = icmp slt i32 %"first_pt_x", 0
  %"is_zero.1" = load i1, i1* %"is_zero.addr"
  br i1 %"is_zero.1", label %"op.||.merge", label %"op.||.eval_b"
"op.||.eval_b":
  %"first_pt_x.1" = load i32, i32* %"first_pt_x.addr"
  %"cmptmp.5" = icmp slt i32 %"first_pt_x.1", 0
  br label %"op.||.merge"
"op.||.merge":
  %"op.||.result" = phi  i1 [1, %"op.&&.merge"], [%"cmptmp.5", %"op.||.eval_b"]
  br i1 %"op.||.result", label %"if.then", label %"if.else"
if.then:
  br label %"if.end"
if.else:
  %"i.addr" = alloca i32
  store i32 0, i32* %"i.addr"
  br label %"while.cond"
if.end:
  ret void
while.cond:
  %"i" = load i32, i32* %"i.addr"
  %"cmptmp.6" = icmp slt i32 %"i", 3
  br i1 %"cmptmp.6", label %"while.body", label %"while.end"
while.body:
  %"i.1" = load i32, i32* %"i.addr"
  %"addtmp.1" = add i32 %"i.1", 1
  store i32 %"addtmp.1", i32* %"i.addr"
  br label %"while.cond"
while.end:
  br label %"if.end"
}

@".str.lit.0" = private constant [12 x i8] c"Hello Atom!\00"
@".str.lit.1" = private constant [19 x i8] c"Uma linha simples.\00"