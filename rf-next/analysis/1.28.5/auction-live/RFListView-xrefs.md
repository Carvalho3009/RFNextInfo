# RF Online NEXT - selected string xrefs

Generated: 2026-07-21T12:18:33.610663500Z

- Program: `libUnreal.so`
- Image base: `00100000`
- Candidate functions: 21

## String occurrences and references

### `RFListView`

- Occurrence: `006a4ee8`
- Occurrence: `006ad447`
- Occurrence: `006adb23`
- Occurrence: `006adbb0`
- Occurrence: `006ba316`
- Occurrence: `007472ee`
- Occurrence: `001a69e8`
- Reference: `adrp+add 05c93624 -> 05c93628 FUN_05c935ac @ 05c935ac`

## FUN_05c935ac @ `05c935ac`

Reasons: ADRP+ADD resolves RFListView @ 001a69e8

```c

void FUN_05c935ac(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a43c470 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001a69e8,0xa43c470,
                 Java_com_epicgames_unreal_NativeCalls_ForwardNotification,0x11a0,0x10,0x10000000,0,
                 &UNK_003d5a06,FUN_05c93678,FUN_01e9f210,&puStack_30,thunk_FUN_03fb77a4,FUN_020be9ec
                );
  }
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail(lRam000000000a43c470);
}


```

## FUN_06f7b700 @ `06f7b700`

Reasons: caller of FUN_05c935ac at 06f7b73c

```c

void FUN_06f7b700(long param_1)

{
  undefined **ppuVar1;
  long lVar2;
  undefined *puVar3;
  long lVar4;
  ulong uVar5;
  long lVar6;
  long *plVar7;
  code *pcVar8;
  undefined8 *puVar9;
  long lVar10;
  undefined8 *puStack_c0;
  int iStack_b8;
  code *pcStack_b0;
  int iStack_a8;
  undefined **ppuStack_a0;
  undefined *apuStack_90 [5];
  long lStack_68;
  
  lVar2 = tpidr_el0;
  lStack_68 = *(long *)(lVar2 + 0x28);
  lVar6 = *(long *)(param_1 + 0x518);
  *(undefined1 *)(param_1 + 0x670) = 0;
  if (lVar6 != 0) {
    lVar4 = FUN_05c935ac();
    if ((*(int *)(*(long *)(lVar6 + 0x10) + 0x38) < *(int *)(lVar4 + 0x38)) ||
       (*(long *)(*(long *)(*(long *)(lVar6 + 0x10) + 0x30) + (long)*(int *)(lVar4 + 0x38) * 8) !=
        lVar4 + 0x30)) {
      lVar4 = FUN_05de05bc();
      if ((*(int *)(lVar4 + 0x38) <= *(int *)(*(long *)(lVar6 + 0x10) + 0x38)) &&
         (*(long *)(*(long *)(*(long *)(lVar6 + 0x10) + 0x30) + (long)*(int *)(lVar4 + 0x38) * 8) ==
          lVar4 + 0x30)) {
        FUN_07034010(lVar6,1);
      }
    }
    else {
      FUN_07020bb0(lVar6,1);
    }
    *(undefined8 *)(param_1 + 0x518) = 0;
  }
  *(undefined8 *)(param_1 + 0x660) = 0;
  *(undefined8 *)(param_1 + 0x510) = 0;
  puVar3 = PTR_DAT_0a11eaf8;
  if (*(int *)(param_1 + 0x550) != 0) {
    plVar7 = *(long **)(param_1 + 0x548);
    lVar6 = (long)*(int *)(param_1 + 0x550) << 3;
    do {
      lVar10 = *plVar7;
      lVar4 = FUN_05de77ec();
      if ((*(int *)(*(long *)(lVar10 + 0x10) + 0x38) < *(int *)(lVar4 + 0x38)) ||
         (*(long *)(*(long *)(*(long *)(lVar10 + 0x10) + 0x30) + (long)*(int *)(lVar4 + 0x38) * 8)
          != lVar4 + 0x30)) {
        lVar10 = *plVar7;
        lVar4 = FUN_05de83c0();
        if (((*(int *)(lVar4 + 0x38) <= *(int *)(*(long *)(lVar10 + 0x10) + 0x38)) &&
            (*(long *)(*(long *)(*(long *)(lVar10 + 0x10) + 0x30) + (long)*(int *)(lVar4 + 0x38) * 8
                      ) == lVar4 + 0x30)) && (lVar4 = *plVar7, lVar4 != 0)) {
          lVar10 = FUN_05de83c0();
          if ((*(int *)(lVar10 + 0x38) <= *(int *)(*(long *)(lVar4 + 0x10) + 0x38)) &&
             (*(long *)(*(long *)(*(long *)(lVar4 + 0x10) + 0x30) +
                       (long)*(int *)(lVar10 + 0x38) * 8) == lVar10 + 0x30)) {
            *(undefined1 *)(lVar4 + 0x428) = 1;
          }
        }
      }
      else {
        lVar4 = *plVar7;
        if (lVar4 != 0) {
          lVar10 = FUN_05de77ec();
          if ((*(int *)(lVar10 + 0x38) <= *(int *)(*(long *)(lVar4 + 0x10) + 0x38)) &&
             (*(long *)(*(long *)(*(long *)(lVar4 + 0x10) + 0x30) +
                       (long)*(int *)(lVar10 + 0x38) * 8) == lVar10 + 0x30)) {
            *(undefined2 *)(lVar4 + 0x450) = 1;
          }
        }
      }
      apuStack_90[0] = &UNK_09c656a8;
      ppuStack_a0 = (undefined **)0x0;
      pcStack_b0 = Java_com_epicgames_unreal_NativeCalls_ForwardNotification;
      FUN_0681dd40(*(undefined8 *)puVar3,*plVar7,&pcStack_b0,0);
      if (pcStack_b0 != (code *)0x0) {
        ppuVar1 = apuStack_90;
        if (ppuStack_a0 != (undefined **)0x0) {
          ppuVar1 = ppuStack_a0;
        }
        (**(code **)(*ppuVar1 + 0x10))();
      }
      lVar6 = lVar6 + -8;
      plVar7 = plVar7 + 1;
    } while (lVar6 != 0);
  }
  *(undefined4 *)(param_1 + 0x550) = 0;
  if (*(int *)(param_1 + 0x554) < 0) {
    FUN_01eafeb0(param_1 + 0x548,0);
  }
  FUN_03fc7818(&pcStack_b0,*(undefined8 *)(param_1 + 0x4b8));
  if (iStack_a8 != 0) {
    lVar6 = (long)iStack_a8 << 3;
    pcVar8 = pcStack_b0;
    do {
      if (*(long *)pcVar8 != *(long *)(param_1 + 0x4a8)) {
        FUN_03fc7e60(*(undefined8 *)(param_1 + 0x4b8));
      }
      lVar6 = lVar6 + -8;
      pcVar8 = pcVar8 + 8;
    } while (lVar6 != 0);
  }
  FUN_03fc7818(&puStack_c0,*(undefined8 *)(param_1 + 0x4c0));
  if (iStack_b8 != 0) {
    lVar6 = (long)iStack_b8 << 3;
    puVar9 = puStack_c0;
    do {
      (**(code **)(*(long *)*puVar9 + 0x2f0))();
      lVar6 = lVar6 + -8;
      puVar9 = puVar9 + 1;
    } while (lVar6 != 0);
  }
  uVar5 = FUN_022a3530(param_1 + 0x558);
  if ((uVar5 & 1) != 0) {
    FUN_022a3668(param_1 + 0x558);
    FUN_05f85efc();
  }
  if (puStack_c0 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  if (pcStack_b0 != (code *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  if (*(long *)(lVar2 + 0x28) == lStack_68) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_069d2558 @ `069d2558`

Reasons: caller of FUN_05c935ac at 069d25c8

```c

void FUN_069d2558(long param_1)

{
  long lVar1;
  long lVar2;
  undefined8 uStack_30;
  long lStack_28;
  
  lVar1 = FUN_03f2b638(param_1 + 0x3c0);
  if (lVar1 != 0) {
    lVar2 = FUN_05b7ad64();
    if ((((*(int *)(lVar2 + 0x38) <= *(int *)(*(long *)(lVar1 + 0x10) + 0x38)) &&
         (*(long *)(*(long *)(*(long *)(lVar1 + 0x10) + 0x30) + (long)*(int *)(lVar2 + 0x38) * 8) ==
          lVar2 + 0x30)) && (*(char *)(lVar1 + 0x4f) != '\0')) &&
       (lVar1 = FUN_03f2a9d4(param_1 + 0x3c0), lVar1 != 0)) {
      lVar2 = FUN_05c935ac();
      if ((*(int *)(lVar2 + 0x38) <= *(int *)(*(long *)(lVar1 + 0x10) + 0x38)) &&
         (*(long *)(*(long *)(*(long *)(lVar1 + 0x10) + 0x30) + (long)*(int *)(lVar2 + 0x38) * 8) ==
          lVar2 + 0x30)) {
        uStack_30 = FUN_03f2b638(param_1 + 0x3c0);
        lVar2 = tpidr_el0;
        lStack_28 = *(long *)(lVar2 + 0x28);
        FUN_03fb8da4(lVar1 + 0x298,&uStack_30,3);
        if (*(long *)(lVar2 + 0x28) == lStack_28) {
          return;
        }
                    /* WARNING: Subroutine does not return */
        __stack_chk_fail();
      }
    }
  }
  return;
}


```

## FUN_06a68980 @ `06a68980`

Reasons: caller of FUN_05c935ac at 06a689a0

```c

void FUN_06a68980(long param_1)

{
  long lVar1;
  long lVar2;
  undefined8 uStack_30;
  long lStack_28;
  
  lVar1 = FUN_03f2a9d4(param_1 + 0x3c0);
  if (lVar1 != 0) {
    lVar2 = FUN_05c935ac();
    if ((*(int *)(lVar2 + 0x38) <= *(int *)(*(long *)(lVar1 + 0x10) + 0x38)) &&
       (*(long *)(*(long *)(*(long *)(lVar1 + 0x10) + 0x30) + (long)*(int *)(lVar2 + 0x38) * 8) ==
        lVar2 + 0x30)) {
      uStack_30 = FUN_03f2b638(param_1 + 0x3c0);
      lVar2 = tpidr_el0;
      lStack_28 = *(long *)(lVar2 + 0x28);
      FUN_03fb8da4(lVar1 + 0x298,&uStack_30,3);
      if (*(long *)(lVar2 + 0x28) == lStack_28) {
        return;
      }
                    /* WARNING: Subroutine does not return */
      __stack_chk_fail();
    }
  }
  return;
}


```

## FUN_06c41adc @ `06c41adc`

Reasons: caller of FUN_05c935ac at 06c41b1c

```c

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_06c41adc(long param_1)

{
  long lVar1;
  long *plVar2;
  int iVar3;
  long lVar4;
  long lVar5;
  long *plVar6;
  long lVar7;
  undefined8 uVar8;
  long lVar9;
  long *plVar10;
  undefined8 uStack_310;
  long lStack_308;
  undefined8 *puStack_300;
  int iStack_2f8;
  undefined4 uStack_2f0;
  undefined4 uStack_2ec;
  undefined4 uStack_2e8;
  undefined4 uStack_2e4;
  undefined4 uStack_2dc;
  undefined1 auStack_2d8 [40];
  undefined1 auStack_2b0 [152];
  undefined1 uStack_218;
  undefined1 auStack_1e0 [16];
  undefined1 auStack_1d0 [32];
  undefined1 uStack_1b0;
  undefined1 auStack_118 [120];
  long *plStack_a0;
  long lStack_98;
  undefined8 uStack_90;
  undefined2 uStack_88;
  undefined6 uStack_86;
  undefined2 uStack_80;
  undefined8 uStack_7e;
  long lStack_68;
  
  lVar1 = tpidr_el0;
  lStack_68 = *(long *)(lVar1 + 0x28);
  lVar4 = FUN_03f2a9d4(param_1 + 0x3c0);
  if (lVar4 == 0) goto LAB_06c41f68;
  lVar5 = FUN_05c935ac();
  if ((*(int *)(*(long *)(lVar4 + 0x10) + 0x38) < *(int *)(lVar5 + 0x38)) ||
     (*(long *)(*(long *)(*(long *)(lVar4 + 0x10) + 0x30) + (long)*(int *)(lVar5 + 0x38) * 8) !=
      lVar5 + 0x30)) goto LAB_06c41f68;
  FUN_03fb8d50(lVar4,*(undefined8 *)(param_1 + 0x480));
  if (*(int *)(lVar4 + 0xb40) != 0) {
    plVar10 = *(long **)(lVar4 + 0xb38);
    lVar5 = (long)*(int *)(lVar4 + 0xb40) << 3;
    do {
      if (((long *)*plVar10 != (long *)0x0) &&
         (plStack_a0 = (long *)*plVar10,
         plVar6 = (long *)(**(code **)(*(long *)(lVar4 + 0x298) + 0x58))((long *)(lVar4 + 0x298)),
         plVar6 != (long *)0x0)) {
        (**(code **)(*plVar6 + 0x3d8))(&uStack_2f0,plVar6,&plStack_a0);
        lVar9 = CONCAT44(uStack_2ec,uStack_2f0);
        plVar6 = (long *)CONCAT44(uStack_2e4,uStack_2e8);
        if (plVar6 != (long *)0x0) {
          FUN_08d08290(1,plVar6 + 1);
          plVar2 = (long *)CONCAT44(uStack_2e4,uStack_2e8);
          if ((plVar2 != (long *)0x0) && (iVar3 = FUN_08d08320(0xffffffff,plVar2 + 1), iVar3 == 1))
          {
            (**(code **)*plVar2)(plVar2);
            iVar3 = FUN_08d08320(0xffffffff,(long)plVar2 + 0xc);
            if (iVar3 == 1) {
              (**(code **)(*plVar2 + 0x10))(plVar2);
            }
          }
        }
        if (lVar9 == 0) {
          lVar9 = 0;
        }
        else {
          lVar9 = *(long *)(lVar9 + -8);
        }
        if ((plVar6 != (long *)0x0) && (iVar3 = FUN_08d08320(0xffffffff,plVar6 + 1), iVar3 == 1)) {
          (**(code **)*plVar6)(plVar6);
          iVar3 = FUN_08d08320(0xffffffff,(long)plVar6 + 0xc);
          if (iVar3 == 1) {
            (**(code **)(*plVar6 + 0x10))(plVar6);
          }
        }
        if (lVar9 != 0) {
          lVar7 = FUN_05c3b0bc();
          if (((*(int *)(lVar7 + 0x38) <= *(int *)(*(long *)(lVar9 + 0x10) + 0x38)) &&
              (*(long *)(*(long *)(*(long *)(lVar9 + 0x10) + 0x30) +
                        (long)*(int *)(lVar7 + 0x38) * 8) == lVar7 + 0x30)) && (lVar9 != param_1)) {
            (**(code **)(**(long **)(lVar9 + 0x470) + 0x378))(*(long **)(lVar9 + 0x470),0);
          }
        }
      }
      lVar5 = lVar5 + -8;
      plVar10 = plVar10 + 1;
    } while (lVar5 != 0);
  }
  lVar4 = FUN_05f0eab8();
  if (lVar4 != *(long *)(*(long *)(param_1 + 0x480) + 0x28)) {
    plVar10 = *(long **)(param_1 + 0x470);
    iVar3 = FUN_040344f4(plVar10);
    (**(code **)(*plVar10 + 0x378))(plVar10,iVar3 == 0);
    FUN_05f482cc(*(undefined8 *)(*(long *)PTR_DAT_0a11eb10 + 0x3860));
    FUN_0656c638();
    goto LAB_06c41f68;
  }
  FUN_05b841a0(&uStack_2f0);
  uStack_218 = 0;
  uStack_2dc = 1;
  uStack_2ec = (undefined4)_UNK_006723a0;
  uStack_2e8 = (undefined4)((ulong)_UNK_006723a0 >> 0x20);
  if (((bRam000000000a4bd5c0 & 1) == 0) && (iVar3 = FUN_08d0333c(0xa4bd5c0), iVar3 != 0)) {
    lStack_98 = _UNK_004a2c82;
    plStack_a0 = _UNK_004a2c7a;
    uStack_88 = _UNK_004a2c92;
    uStack_90 = _UNK_004a2c8a;
    uStack_7e = _UNK_004a2c9c;
    uStack_86 = _UNK_004a2c94;
    uStack_80 = _UNK_004a2c9a;
    FUN_0206e308(&lStack_308,&plStack_a0,1);
    lRam000000000a4bd5b8 = lStack_308;
    FUN_08d03480(0xa4bd5c0);
  }
  lVar4 = lRam000000000a4bd5b8;
  plStack_a0 = (long *)0x0;
  lStack_98 = 0;
  FUN_022a3430(&plStack_a0,param_1);
  lStack_98 = lVar4;
  if ((lVar4 != 0) && (lVar4 = FUN_022a3668(&plStack_a0), lVar4 != 0)) {
    FUN_022573b4(lVar4,lStack_98);
  }
  FUN_0221900c(auStack_118,&plStack_a0);
  FUN_0206e308(&lStack_308,&UNK_004dde92,1);
  FUN_05f0a9e4(&lStack_308,0);
  FUN_01f60f14(&plStack_a0);
  FUN_01f552fc(auStack_2d8,&plStack_a0);
  if (plStack_a0 != (long *)0x0) {
    (**(code **)(*plStack_a0 + 0x18))();
  }
  FUN_0206e308(&lStack_308,&UNK_0050aaf0,1);
  FUN_05f0a9e4(&lStack_308,0);
  FUN_01f60f14(&plStack_a0);
  FUN_01f552fc(auStack_2b0,&plStack_a0);
  if (plStack_a0 != (long *)0x0) {
    (**(code **)(*plStack_a0 + 0x18))();
  }
  uStack_1b0 = 0;
  FUN_0206e308(&lStack_308,&UNK_004f95fc,1);
  FUN_05f0a9e4(&lStack_308,0);
  FUN_01f60f14(&plStack_a0);
  FUN_01f552fc(auStack_1e0,&plStack_a0);
  if (plStack_a0 != (long *)0x0) {
    (**(code **)(*plStack_a0 + 0x18))();
  }
  FUN_0206e308(&lStack_308,&UNK_004e5938,1);
  FUN_05f0a9e4(&lStack_308,0);
  FUN_01f60f14(&plStack_a0);
  FUN_01f552fc(auStack_1d0,&plStack_a0);
  if (plStack_a0 != (long *)0x0) {
    (**(code **)(*plStack_a0 + 0x18))();
  }
  uVar8 = *(undefined8 *)PTR_DAT_0a11eb58;
  FUN_0206e5c8(&uStack_310,&UNK_008c1cb5,1);
  puStack_300 = (undefined8 *)0x0;
  iStack_2f8 = 0;
  lVar4 = FUN_05f7c848(uVar8,1,0,0,uStack_310,0,&puStack_300,0);
  if (iStack_2f8 == 0) {
LAB_06c41f04:
    if (puStack_300 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  else if (puStack_300 != (undefined8 *)0x0) {
    (**(code **)*puStack_300)();
    FUN_01ec217c(&puStack_300,0,0,0x10);
    iStack_2f8 = 0;
    goto LAB_06c41f04;
  }
  if (lVar4 != 0) {
    FUN_06e2ffa4(lVar4,&uStack_2f0);
  }
  FUN_05b84330(&uStack_2f0);
LAB_06c41f68:
  if (*(long *)(lVar1 + 0x28) == lStack_68) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_06a2d390 @ `06a2d390`

Reasons: caller of FUN_05c935ac at 06a2d554

```c

void FUN_06a2d390(long param_1)

{
  long lVar1;
  undefined4 uVar2;
  ulong uVar3;
  long lVar4;
  long lVar5;
  long lVar6;
  long lVar7;
  float *pfVar8;
  undefined8 uVar9;
  double dVar10;
  double dVar11;
  double dVar12;
  double dStack_80;
  double dStack_78;
  undefined8 uStack_70;
  undefined8 *puStack_68;
  int iStack_60;
  long lStack_58;
  
  lVar1 = tpidr_el0;
  lStack_58 = *(long *)(lVar1 + 0x28);
  if ((*(byte *)(param_1 + 0x4fb) & 1) != 0) goto LAB_06a2d3c4;
  if (*(char *)(param_1 + 0x510) == '\0') {
    lVar4 = *(long *)(param_1 + 0x520);
  }
  else {
    uVar3 = FUN_022a3530(param_1 + 0x514);
    if ((uVar3 & 1) == 0) goto LAB_06a2d3c4;
    lVar4 = FUN_022a3668(param_1 + 0x514);
  }
  if (lVar4 == 0) goto LAB_06a2d3c4;
  if (((*(int *)(lVar4 + 0x38) != 0) && (*(long **)(lVar4 + 0x30) != (long *)0x0)) &&
     (uVar3 = (**(code **)(**(long **)(lVar4 + 0x30) + 0x38))(), (uVar3 & 1) != 0)) {
    (**(code **)(**(long **)(lVar4 + 0x30) + 0x60))(*(long **)(lVar4 + 0x30),lVar4);
  }
  if (*(char *)(lVar4 + 0x46) == '\0') goto LAB_06a2d3c4;
  uVar9 = *(undefined8 *)PTR_DAT_0a11eb58;
  FUN_0206e5c8(&uStack_70,&UNK_008c1cb5,1);
  puStack_68 = (undefined8 *)0x0;
  iStack_60 = 0;
  lVar5 = FUN_0692e82c(uVar9,1,0,0,uStack_70,0,&puStack_68,0);
  if (iStack_60 == 0) {
LAB_06a2d4e8:
    if (puStack_68 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  else if (puStack_68 != (undefined8 *)0x0) {
    (**(code **)*puStack_68)();
    FUN_01ec217c(&puStack_68,0,0,0x10);
    iStack_60 = 0;
    goto LAB_06a2d4e8;
  }
  if (lVar5 != 0) {
    lVar6 = thunk_FUN_03ffa0e4(param_1);
    dVar12 = (double)((float)((ulong)*(undefined8 *)(lVar6 + 0x1c) >> 0x20) *
                      (float)*(undefined8 *)PTR_DAT_0a118868 +
                      (float)((ulong)*(undefined8 *)(lVar6 + 0x24) >> 0x20) *
                      *(float *)(PTR_DAT_0a118868 + 4) +
                     (float)((ulong)*(undefined8 *)(lVar6 + 0x2c) >> 0x20));
    dVar10 = (double)FUN_05f4e8b0((double)((float)*(undefined8 *)(lVar6 + 0x1c) *
                                           (float)*(undefined8 *)PTR_DAT_0a118868 +
                                           (float)*(undefined8 *)(lVar6 + 0x24) *
                                           *(float *)(PTR_DAT_0a118868 + 4) +
                                          (float)*(undefined8 *)(lVar6 + 0x2c)),param_1);
    lVar6 = FUN_03f2a9d4(param_1 + 0x3c0);
    if (lVar6 != 0) {
      lVar7 = FUN_05c935ac();
      if ((*(int *)(lVar7 + 0x38) <= *(int *)(*(long *)(lVar6 + 0x10) + 0x38)) &&
         (*(long *)(*(long *)(*(long *)(lVar6 + 0x10) + 0x30) + (long)*(int *)(lVar7 + 0x38) * 8) ==
          lVar7 + 0x30)) {
        lVar6 = FUN_02b972a8(lVar6);
        dVar11 = *(double *)(lVar6 + 0x10);
        pfVar8 = (float *)thunk_FUN_03ffa0e4(*(undefined8 *)(param_1 + 0x470));
        dStack_80 = dVar10 + (double)(*pfVar8 * (float)dVar11 * 0.5);
        dStack_78 = dVar12;
        if (*(char *)(lVar4 + 0x4e) == '\x03') {
          if (*(long **)(lVar4 + 0x60) == (long *)0x0) {
            uVar2 = 0;
          }
          else {
            uVar2 = (**(code **)(**(long **)(lVar4 + 0x60) + 0x28))();
          }
          FUN_069fcacc(lVar5,uVar2,&dStack_80);
        }
        else if (*(char *)(lVar4 + 0x4e) == '\x02') {
          if (*(long **)(lVar4 + 0x60) == (long *)0x0) {
            uVar2 = 0;
          }
          else {
            uVar2 = (**(code **)(**(long **)(lVar4 + 0x60) + 0x28))();
          }
          FUN_069fc988(lVar5,uVar2,&dStack_80);
        }
      }
    }
  }
LAB_06a2d3c4:
  if (*(long *)(lVar1 + 0x28) != lStack_58) {
                    /* WARNING: Subroutine does not return */
    __stack_chk_fail();
  }
  return;
}


```

## FUN_06e1491c @ `06e1491c`

Reasons: caller of FUN_05c935ac at 06e149c0

```c

void FUN_06e1491c(long param_1)

{
  char *pcVar1;
  byte bVar2;
  double dVar3;
  undefined1 auVar4 [16];
  undefined1 auVar5 [16];
  char cVar6;
  undefined8 *puVar7;
  undefined8 *puVar8;
  bool bVar9;
  int iVar10;
  int iVar11;
  long lVar12;
  long lVar13;
  long *plVar14;
  long lVar15;
  float fVar16;
  float fVar17;
  float fVar18;
  undefined4 uVar19;
  undefined4 uVar20;
  float fVar21;
  float fVar22;
  undefined1 auVar23 [16];
  float fVar24;
  double dVar25;
  double dVar26;
  float fStack_c8;
  float fStack_c4;
  undefined8 uStack_c0;
  undefined8 uStack_b8;
  undefined8 uStack_b0;
  char acStack_a8 [8];
  undefined8 *puStack_a0;
  ulong uStack_98;
  undefined1 auStack_88 [24];
  char acStack_70 [4];
  undefined1 uStack_6c;
  undefined8 *puStack_68;
  ulong uStack_60;
  long lStack_58;
  
  lVar12 = FUN_03f2b638(param_1 + 0x3c0);
  if (lVar12 != 0) {
    lVar13 = FUN_05ae37bc();
    if ((*(int *)(lVar13 + 0x38) <= *(int *)(*(long *)(lVar12 + 0x10) + 0x38)) &&
       (*(long *)(*(long *)(*(long *)(lVar12 + 0x10) + 0x30) + (long)*(int *)(lVar13 + 0x38) * 8) ==
        lVar13 + 0x30)) {
      lVar12 = FUN_03f2a9d4(param_1 + 0x3c0);
      if (lVar12 != 0) {
        lVar13 = FUN_05c935ac();
        if ((*(int *)(lVar13 + 0x38) <= *(int *)(*(long *)(lVar12 + 0x10) + 0x38)) &&
           (*(long *)(*(long *)(*(long *)(lVar12 + 0x10) + 0x30) + (long)*(int *)(lVar13 + 0x38) * 8
                     ) == lVar13 + 0x30)) goto LAB_06e149f0;
      }
      lVar12 = 0;
LAB_06e149f0:
      lVar13 = FUN_03f2b638(param_1 + 0x3c0);
      if (lVar13 != 0) {
        FUN_05ae37bc();
      }
      lVar13 = tpidr_el0;
      lVar15 = *(long *)(lVar13 + 0x28);
      FUN_03fb8da4(lVar12 + 0x298,&stack0xffffffffffffffd0,3);
      if (*(long *)(lVar13 + 0x28) == lVar15) {
        return;
      }
                    /* WARNING: Subroutine does not return */
      __stack_chk_fail();
    }
  }
  lVar12 = FUN_03f2b638(param_1 + 0x3c0);
  if (lVar12 == 0) {
    return;
  }
  lVar13 = FUN_05ae3920();
  if (*(int *)(*(long *)(lVar12 + 0x10) + 0x38) < *(int *)(lVar13 + 0x38)) {
    return;
  }
  if (*(long *)(*(long *)(*(long *)(lVar12 + 0x10) + 0x30) + (long)*(int *)(lVar13 + 0x38) * 8) !=
      lVar13 + 0x30) {
    return;
  }
  bVar2 = *(byte *)(lVar12 + 0x79);
  *(byte *)(lVar12 + 0x79) = bVar2 ^ 1;
  uVar19 = 0x43340000;
  if (bVar2 != 0) {
    uVar19 = 0;
  }
  lVar13 = *(long *)(param_1 + 0x3e0);
  *(undefined4 *)(lVar13 + 0xc0) = uVar19;
  lVar12 = tpidr_el0;
  lStack_58 = *(long *)(lVar12 + 0x28);
  if (((*(long *)(lVar13 + 0x108) == 0) ||
      (plVar14 = *(long **)(lVar13 + 0x110), plVar14 == (long *)0x0)) || ((int)plVar14[1] < 1)) {
    plVar14 = *(long **)(lVar13 + 0x100);
    if (plVar14 == (long *)0x0) goto LAB_03fffeb4;
    iVar11 = (int)plVar14[1];
    do {
      if (iVar11 == 0) goto LAB_03fffeb4;
      iVar10 = FUN_08d07dc0(iVar11,iVar11 + 1,plVar14 + 1);
      bVar9 = iVar10 != iVar11;
      iVar11 = iVar10;
    } while (bVar9);
    lVar15 = *(long *)(lVar13 + 0xf8);
  }
  else {
    iVar11 = (int)plVar14[1];
    do {
      if (iVar11 == 0) goto LAB_03fffeb4;
      iVar10 = FUN_08d07dc0(iVar11,iVar11 + 1,plVar14 + 1);
      bVar9 = iVar10 != iVar11;
      iVar11 = iVar10;
    } while (bVar9);
    lVar15 = *(long *)(lVar13 + 0x108);
    FUN_08d08290(1,plVar14 + 1);
    iVar11 = FUN_08d08320(0xffffffff,plVar14 + 1);
    if (iVar11 == 1) {
      (**(code **)*plVar14)(plVar14);
      iVar11 = FUN_08d08320(0xffffffff,(long)plVar14 + 0xc);
      if (iVar11 == 1) {
        (**(code **)(*plVar14 + 0x10))(plVar14);
      }
    }
  }
  if (lVar15 != 0) {
    if (((bRam000000000a35a3f0 & 1) == 0) && (iVar11 = FUN_08d0333c(0xa35a3f0), iVar11 != 0)) {
      dRam000000000a35a3c0 = *(double *)(PTR_DAT_0a118878 + 8);
      dRam000000000a35a3b8 = *(double *)PTR_DAT_0a118878;
      dRam000000000a35a3d0 = SUB168(*(undefined1 (*) [16])PTR_DAT_0a118880,8);
      dRam000000000a35a3c8 = SUB168(*(undefined1 (*) [16])PTR_DAT_0a118880,0);
      fRam000000000a35a3e8 = 0.0;
      dRam000000000a35a3d8 = dRam000000000a35a3b8;
      dRam000000000a35a3e0 = dRam000000000a35a3c0;
      FUN_08d03480(0xa35a3f0);
    }
    dVar25 = *(double *)(lVar13 + 0xa0);
    dVar26 = *(double *)(lVar13 + 0xa8);
    if ((dRam000000000a35a3c8 == dVar25) && (dRam000000000a35a3d0 == dVar26)) {
      dVar3 = *(double *)(lVar13 + 0xb0);
      uVar19 = SUB84(dVar3,0);
      uVar20 = (undefined4)((ulong)dVar3 >> 0x20);
      if ((((dRam000000000a35a3d8 != dVar3) || (dRam000000000a35a3e0 != *(double *)(lVar13 + 0xb8)))
          || (fRam000000000a35a3e8 != *(float *)(lVar13 + 0xc0))) ||
         ((dRam000000000a35a3b8 != *(double *)(lVar13 + 0x90) ||
          (dRam000000000a35a3c0 != *(double *)(lVar13 + 0x98))))) goto LAB_03fffcb0;
      acStack_70[0] = '\0';
      uStack_6c = 1;
      pcVar1 = acStack_70;
      puStack_68 = (undefined8 *)0x0;
      uStack_60 = 0;
      FUN_02432a1c(lVar15 + 0x198,lVar15,auStack_88);
      if ((int)uStack_60 == 0) {
LAB_03fffc94:
        puVar7 = puStack_a0;
        puVar8 = (undefined8 *)0x0;
        cVar6 = acStack_70[0];
        if (puStack_68 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
          FUN_01f18da4();
        }
      }
      else {
        puVar7 = puStack_a0;
        puVar8 = (undefined8 *)0x0;
        cVar6 = acStack_70[0];
        if (puStack_68 != (undefined8 *)0x0) {
          (**(code **)*puStack_68)();
          FUN_01ec217c(&puStack_68,0,0,0x10);
          uStack_60 = uStack_60 & 0xffffffff00000000;
          goto LAB_03fffc94;
        }
      }
    }
    else {
      uVar19 = (undefined4)*(undefined8 *)(lVar13 + 0xb0);
      uVar20 = (undefined4)((ulong)*(undefined8 *)(lVar13 + 0xb0) >> 0x20);
LAB_03fffcb0:
      fVar17 = 0.0;
      fVar16 = 0.0;
      if ((double)CONCAT44(uVar20,uVar19) != 0.0) {
        fVar16 = (float)NEON_fminnm((float)(double)CONCAT44(uVar20,uVar19),0x42b20000);
        if (fVar16 <= -89.0) {
          fVar16 = -89.0;
        }
        fVar16 = (float)tanf((90.0 - fVar16) * 0.017453292);
        fVar16 = 1.0 / fVar16;
      }
      fVar21 = (float)dVar25;
      fVar22 = (float)dVar26;
      if (*(double *)(lVar13 + 0xb8) != 0.0) {
        fVar17 = (float)NEON_fminnm((float)*(double *)(lVar13 + 0xb8),0x42b20000);
        if (fVar17 <= -89.0) {
          fVar17 = -89.0;
        }
        fVar17 = (float)tanf((90.0 - fVar17) * 0.017453292);
        fVar17 = 1.0 / fVar17;
      }
      sincosf(*(float *)(lVar13 + 0xc0) * 0.017453292,&fStack_c4,&fStack_c8);
      acStack_a8[0] = '\x01';
      acStack_a8[4] = 1;
      puStack_a0 = (undefined8 *)0x0;
      uStack_98 = 0;
      fVar18 = fVar16 * 0.0 + fVar21;
      fVar21 = fVar17 * fVar21 + 0.0;
      fVar16 = fVar16 * fVar22 + 0.0;
      fVar22 = fVar17 * 0.0 + fVar22;
      auVar23._4_4_ = fVar21;
      auVar23._0_4_ = fVar18;
      auVar23._8_4_ = fVar16;
      auVar23._12_4_ = fVar22;
      auVar23 = NEON_rev64(auVar23,4);
      fVar21 = fVar21 * fStack_c8;
      fVar22 = fVar22 * fStack_c8;
      fVar17 = auVar23._4_4_ * fStack_c4;
      fVar24 = auVar23._12_4_ * fStack_c4;
      auVar4._4_4_ = fVar21 - fVar17;
      auVar4._0_4_ = fVar18 * fStack_c8 - auVar23._0_4_ * fStack_c4;
      auVar4._8_4_ = fVar16 * fStack_c8 - auVar23._8_4_ * fStack_c4;
      auVar4._12_4_ = fVar22 - fVar24;
      auVar23 = NEON_rev64(auVar4,4);
      pcVar1 = acStack_a8;
      auVar5._12_4_ = (int)((ulong)*(undefined8 *)(lVar13 + 0x98) >> 0x20);
      auVar5._0_12_ = *(undefined1 (*) [12])(lVar13 + 0x90);
      uStack_b0 = CONCAT44((float)auVar5._8_8_,
                           (float)SUB128(*(undefined1 (*) [12])(lVar13 + 0x90),0));
      uStack_b8 = CONCAT44(fVar22 + fVar24,auVar23._12_4_);
      uStack_c0 = CONCAT44(fVar21 + fVar17,auVar23._4_4_);
      FUN_02432a1c(lVar15 + 0x198,lVar15,&uStack_c0);
      if ((int)uStack_98 != 0) {
        puVar7 = (undefined8 *)0x0;
        puVar8 = puStack_68;
        cVar6 = acStack_a8[0];
        if (puStack_a0 == (undefined8 *)0x0) goto joined_r0x03fffe60;
        (**(code **)*puStack_a0)();
        FUN_01ec217c(&puStack_a0,0,0,0x10);
        uStack_98 = uStack_98 & 0xffffffff00000000;
      }
      puVar7 = (undefined8 *)0x0;
      puVar8 = puStack_68;
      cVar6 = acStack_a8[0];
      if (puStack_a0 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
        FUN_01f18da4();
      }
    }
joined_r0x03fffe60:
    puStack_68 = puVar8;
    puStack_a0 = puVar7;
    if (cVar6 != '\0') {
      *pcVar1 = '\0';
    }
  }
  iVar11 = FUN_08d08320(0xffffffff,plVar14 + 1);
  if (iVar11 == 1) {
    (**(code **)*plVar14)(plVar14);
    iVar11 = FUN_08d08320(0xffffffff,(long)plVar14 + 0xc);
    if (iVar11 == 1) {
      (**(code **)(*plVar14 + 0x10))(plVar14);
    }
  }
LAB_03fffeb4:
  if (*(long *)(lVar12 + 0x28) == lStack_58) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_069112e4 @ `069112e4`

Reasons: caller of FUN_05c935ac at 069113d4

```c

void FUN_069112e4(long param_1,ulong param_2)

{
  byte bVar1;
  long lVar2;
  ulong uVar3;
  undefined8 uVar4;
  long lVar5;
  
  if ((param_2 & 1) != 0) {
    lVar2 = FUN_022a3668(param_1 + 0x3f8);
    bVar1 = *(byte *)(lVar2 + 0x30);
    lVar2 = FUN_022a3668(param_1 + 0x3f8);
    *(byte *)(lVar2 + 0x30) = bVar1 ^ 1;
    lVar2 = FUN_022a3668(param_1 + 0x3f8);
    if (*(char *)(lVar2 + 0x30) == '\0') {
      FUN_03f3af14(*(undefined8 *)(param_1 + 0x3c8),0);
      FUN_05f4cb4c(*(undefined8 *)(param_1 + 1000),0,1,1);
      lVar2 = FUN_03f2a9d4(param_1 + 0x3c0);
      if (lVar2 != 0) {
        lVar5 = FUN_05c935ac();
        if ((*(int *)(lVar5 + 0x38) <= *(int *)(*(long *)(lVar2 + 0x10) + 0x38)) &&
           (*(long *)(*(long *)(*(long *)(lVar2 + 0x10) + 0x30) + (long)*(int *)(lVar5 + 0x38) * 8)
            == lVar5 + 0x30)) {
          FUN_03fb8768(lVar2);
        }
      }
    }
    else {
      FUN_03f3af14(*(undefined8 *)(param_1 + 0x3c8),1);
      FUN_05f4cb4c(*(undefined8 *)(param_1 + 1000),1,4,1);
    }
    lVar2 = FUN_022a3668(param_1 + 0x3f8);
    if (((*(int *)(lVar2 + 0x40) != 0) && (*(long **)(lVar2 + 0x38) != (long *)0x0)) &&
       (uVar3 = (**(code **)(**(long **)(lVar2 + 0x38) + 0x38))(), (uVar3 & 1) != 0)) {
      lVar2 = FUN_022a3668(param_1 + 0x3f8);
      uVar4 = FUN_022a3668(param_1 + 0x3f8);
                    /* WARNING: Could not recover jumptable at 0x06911398. Too many branches */
                    /* WARNING: Treating indirect jump as call */
      (**(code **)(**(long **)(lVar2 + 0x38) + 0x60))(*(long **)(lVar2 + 0x38),uVar4);
      return;
    }
  }
  return;
}


```

## FUN_06a380f0 @ `06a380f0`

Reasons: caller of FUN_05c935ac at 06a38110

```c

void FUN_06a380f0(long param_1)

{
  long *plVar1;
  long lVar2;
  long lVar3;
  
  lVar2 = FUN_03f2a9d4(*(long *)(param_1 + 0x20) + 0x3c0);
  if (lVar2 != 0) {
    lVar3 = FUN_05c935ac();
    if ((*(int *)(lVar3 + 0x38) <= *(int *)(*(long *)(lVar2 + 0x10) + 0x38)) &&
       (*(long *)(*(long *)(*(long *)(lVar2 + 0x10) + 0x30) + (long)*(int *)(lVar3 + 0x38) * 8) ==
        lVar3 + 0x30)) {
      FUN_03fb7418(lVar2,uRam000000000a4b1470);
      FUN_03f2c164(lVar2 + 0x1c8,0);
      *(undefined4 *)(lVar2 + 400) = 0;
      if (*(int *)(lVar2 + 0x194) < 0) {
        FUN_01f016e8(lVar2 + 0x188,0);
        plVar1 = *(long **)(lVar2 + 0x288);
      }
      else {
        plVar1 = *(long **)(lVar2 + 0x288);
      }
      if (plVar1 != (long *)0x0) {
                    /* WARNING: Could not recover jumptable at 0x03fba300. Too many branches */
                    /* WARNING: Treating indirect jump as call */
        (**(code **)(*plVar1 + 600))();
        return;
      }
      return;
    }
  }
  return;
}


```

## FUN_06a38168 @ `06a38168`

Reasons: caller of FUN_05c935ac at 06a3819c

```c

uint FUN_06a38168(long param_1)

{
  uint uVar1;
  long lVar2;
  long lVar3;
  
  uVar1 = FUN_022a3530(param_1 + 0x18);
  if (((uVar1 & 1) != 0) && (lVar2 = FUN_03f2a9d4(*(long *)(param_1 + 0x20) + 0x3c0), lVar2 != 0)) {
    lVar3 = FUN_05c935ac();
    if ((*(int *)(lVar3 + 0x38) <= *(int *)(*(long *)(lVar2 + 0x10) + 0x38)) &&
       (*(long *)(*(long *)(*(long *)(lVar2 + 0x10) + 0x30) + (long)*(int *)(lVar3 + 0x38) * 8) ==
        lVar3 + 0x30)) {
      FUN_03fb7418(lVar2,uRam000000000a4b1470);
      FUN_03fba2c0(lVar2);
      return uVar1 & 1;
    }
  }
  return uVar1 & 1;
}


```

## FUN_06c42f74 @ `06c42f74`

Reasons: caller of FUN_05c935ac at 06c42fe8

```c

void FUN_06c42f74(long param_1,ulong param_2)

{
  long lVar1;
  long *plVar2;
  int iVar3;
  long lVar4;
  long lVar5;
  long *plVar6;
  long lVar7;
  long lVar8;
  long *plVar9;
  long lStack_80;
  long lStack_78;
  long *plStack_70;
  long lStack_68;
  
  lVar1 = tpidr_el0;
  lStack_68 = *(long *)(lVar1 + 0x28);
  if (*(long *)(param_1 + 0x480) != 0) {
    lVar4 = FUN_05f0eab8();
    (**(code **)(**(long **)(param_1 + 0x468) + 0x378))
              (*(long **)(param_1 + 0x468),lVar4 == *(long *)(*(long *)(param_1 + 0x480) + 0x28));
    lVar4 = FUN_03f2a9d4(param_1 + 0x3c0);
    if (lVar4 != 0) {
      lVar5 = FUN_05c935ac();
      if ((((*(int *)(lVar5 + 0x38) <= *(int *)(*(long *)(lVar4 + 0x10) + 0x38)) &&
           (*(long *)(*(long *)(*(long *)(lVar4 + 0x10) + 0x30) + (long)*(int *)(lVar5 + 0x38) * 8)
            == lVar5 + 0x30)) && ((param_2 & 1) != 0)) && (*(int *)(lVar4 + 0xb40) != 0)) {
        plVar9 = *(long **)(lVar4 + 0xb38);
        lVar5 = (long)*(int *)(lVar4 + 0xb40) << 3;
        do {
          if ((*plVar9 != 0) &&
             (lStack_80 = *plVar9,
             plVar6 = (long *)(**(code **)(*(long *)(lVar4 + 0x298) + 0x58))
                                        ((long *)(lVar4 + 0x298)), plVar6 != (long *)0x0)) {
            (**(code **)(*plVar6 + 0x3d8))(&lStack_78,plVar6,&lStack_80);
            plVar6 = plStack_70;
            lVar8 = lStack_78;
            if ((plStack_70 != (long *)0x0) &&
               ((FUN_08d08290(1,plStack_70 + 1), plVar2 = plStack_70, plStack_70 != (long *)0x0 &&
                (iVar3 = FUN_08d08320(0xffffffff,plStack_70 + 1), iVar3 == 1)))) {
              (**(code **)*plVar2)(plVar2);
              iVar3 = FUN_08d08320(0xffffffff,(long)plVar2 + 0xc);
              if (iVar3 == 1) {
                (**(code **)(*plVar2 + 0x10))(plVar2);
              }
            }
            if (lVar8 == 0) {
              lVar8 = 0;
            }
            else {
              lVar8 = *(long *)(lVar8 + -8);
            }
            if ((plVar6 != (long *)0x0) && (iVar3 = FUN_08d08320(0xffffffff,plVar6 + 1), iVar3 == 1)
               ) {
              (**(code **)*plVar6)(plVar6);
              iVar3 = FUN_08d08320(0xffffffff,(long)plVar6 + 0xc);
              if (iVar3 == 1) {
                (**(code **)(*plVar6 + 0x10))(plVar6);
              }
            }
            if (lVar8 != 0) {
              lVar7 = FUN_05c3b0bc();
              if (((*(int *)(lVar7 + 0x38) <= *(int *)(*(long *)(lVar8 + 0x10) + 0x38)) &&
                  (*(long *)(*(long *)(*(long *)(lVar8 + 0x10) + 0x30) +
                            (long)*(int *)(lVar7 + 0x38) * 8) == lVar7 + 0x30)) &&
                 (lVar8 != param_1)) {
                (**(code **)(**(long **)(lVar8 + 0x470) + 0x378))(*(long **)(lVar8 + 0x470),0);
              }
            }
          }
          lVar5 = lVar5 + -8;
          plVar9 = plVar9 + 1;
        } while (lVar5 != 0);
      }
    }
  }
  if (*(long *)(lVar1 + 0x28) == lStack_68) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_06e14254 @ `06e14254`

Reasons: caller of FUN_05c935ac at 06e143f0

```c

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_06e14254(long param_1,long param_2)

{
  long lVar1;
  undefined4 uVar2;
  long lVar3;
  long lVar4;
  undefined8 uVar5;
  undefined1 uVar6;
  undefined *puVar7;
  long *plVar8;
  undefined1 auStack_70 [8];
  long *aplStack_68 [2];
  long *aplStack_58 [2];
  long lStack_48;
  
  lVar1 = tpidr_el0;
  lStack_48 = *(long *)(lVar1 + 0x28);
  if (param_2 != 0) {
    lVar3 = FUN_05ae37bc();
    if ((*(int *)(*(long *)(param_2 + 0x10) + 0x38) < *(int *)(lVar3 + 0x38)) ||
       (*(long *)(*(long *)(*(long *)(param_2 + 0x10) + 0x30) + (long)*(int *)(lVar3 + 0x38) * 8) !=
        lVar3 + 0x30)) {
      lVar3 = FUN_05ae3920();
      if ((*(int *)(lVar3 + 0x38) <= *(int *)(*(long *)(param_2 + 0x10) + 0x38)) &&
         (*(long *)(*(long *)(*(long *)(param_2 + 0x10) + 0x30) + (long)*(int *)(lVar3 + 0x38) * 8)
          == lVar3 + 0x30)) {
        uVar6 = *(undefined1 *)(param_2 + 0x78);
        (**(code **)(**(long **)(param_1 + 0x3c8) + 0x378))(*(long **)(param_1 + 0x3c8),0);
        uVar2 = 0;
        if (*(char *)(param_2 + 0x79) != '\0') {
          uVar2 = 0x43340000;
        }
        FUN_03ffde44(uVar2,*(undefined8 *)(param_1 + 0x3e0));
        plVar8 = *(long **)(param_1 + 0x3d8);
        if (*(int *)(param_2 + 0x50) == 0) {
          puVar7 = &UNK_0065d83a;
        }
        else {
          puVar7 = *(undefined **)(param_2 + 0x48);
        }
        FUN_0206e308(auStack_70,puVar7,1);
        FUN_01f60eb0(aplStack_68,auStack_70);
        (**(code **)(*plVar8 + 0x3a0))(plVar8,aplStack_68);
        if (aplStack_68[0] != (long *)0x0) {
          (**(code **)(*aplStack_68[0] + 0x18))();
        }
        lVar3 = FUN_0221dcc8(*(long *)(param_2 + 0x90) + 0x28);
        if (lVar3 == 0) {
LAB_06e1450c:
          uVar5 = *(undefined8 *)(param_1 + 0x3d0);
          lVar3 = 0;
        }
        else {
          lVar4 = FUN_05983e58();
          if ((*(int *)(*(long *)(lVar3 + 0x10) + 0x38) < *(int *)(lVar4 + 0x38)) ||
             (*(long *)(*(long *)(*(long *)(lVar3 + 0x10) + 0x30) + (long)*(int *)(lVar4 + 0x38) * 8
                       ) != lVar4 + 0x30)) goto LAB_06e1450c;
          uVar5 = *(undefined8 *)(param_1 + 0x3d0);
        }
        FUN_03fadc3c(uVar5,lVar3);
        goto LAB_06e1444c;
      }
    }
    else {
      (**(code **)(**(long **)(param_1 + 0x3c8) + 0x378))(*(long **)(param_1 + 0x3c8),1);
      if (*(char *)(param_2 + 0x8c) == '\0') {
        FUN_06e14530(param_1);
        FUN_06a1f0c8(*(undefined8 *)(param_1 + 0x3f0),param_2 + 0x48,1);
        plVar8 = *(long **)(param_1 + 1000);
      }
      else {
        FUN_06e14738(param_1);
        FUN_06a1f0c8(*(undefined8 *)(param_1 + 0x3f0),param_2 + 0x48,1);
        plVar8 = *(long **)(param_1 + 1000);
      }
      if ((plVar8 != (long *)0x0) && ((*(uint *)(plVar8 + 1) >> 0x1e & 1) == 0)) {
        FUN_01f60f14(aplStack_58,param_2 + 0x58);
        (**(code **)(*plVar8 + 0x3a0))(plVar8,aplStack_58);
        if (aplStack_58[0] != (long *)0x0) {
          (**(code **)(*aplStack_58[0] + 0x18))();
        }
        FUN_05f4cb4c(*(undefined8 *)(param_1 + 1000),1 < *(int *)(param_2 + 0x60),1,1);
      }
      lVar3 = FUN_03f2a9d4(param_1 + 0x3c0);
      if (lVar3 != 0) {
        lVar4 = FUN_05c935ac();
        if (((*(int *)(lVar4 + 0x38) <= *(int *)(*(long *)(lVar3 + 0x10) + 0x38)) &&
            (*(long *)(*(long *)(*(long *)(lVar3 + 0x10) + 0x30) + (long)*(int *)(lVar4 + 0x38) * 8)
             == lVar4 + 0x30)) && (*(int *)(param_2 + 0x88) == _DAT_0a4a0cb4)) {
          FUN_03fb8d50(lVar3,param_2);
          uVar6 = 1;
          goto LAB_06e1444c;
        }
      }
    }
  }
  uVar6 = 1;
LAB_06e1444c:
  FUN_05f4cb4c(param_1,uVar6,1,1);
  if (*(long *)(lVar1 + 0x28) == lStack_48) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_06eace24 @ `06eace24`

Reasons: caller of FUN_05c935ac at 06eacec0

```c

void FUN_06eace24(long param_1,ulong param_2)

{
  int iVar1;
  byte bVar2;
  long lVar3;
  ulong uVar4;
  undefined8 uVar5;
  
  if ((param_2 & 1) != 0) {
    lVar3 = FUN_022a3668(param_1 + 0x428);
    bVar2 = *(byte *)(lVar3 + 0x2c);
    lVar3 = FUN_022a3668(param_1 + 0x428);
    *(byte *)(lVar3 + 0x2c) = bVar2 ^ 1;
    lVar3 = FUN_022a3668(param_1 + 0x428);
    if (*(char *)(lVar3 + 0x2c) == '\0') {
      FUN_03f3af14(*(undefined8 *)(param_1 + 0x3c8),0);
      FUN_05f4cb4c(*(undefined8 *)(param_1 + 0x418),0,1,1);
      uVar5 = FUN_03f2a9d4(param_1 + 0x3c0);
      FUN_05c935ac();
      FUN_03fb8768(uVar5);
      lVar3 = FUN_022a3668(param_1 + 0x428);
      iVar1 = *(int *)(lVar3 + 0x38);
    }
    else {
      FUN_03f3af14(*(undefined8 *)(param_1 + 0x3c8),1);
      FUN_05f4cb4c(*(undefined8 *)(param_1 + 0x418),1,4,1);
      lVar3 = FUN_022a3668(param_1 + 0x428);
      iVar1 = *(int *)(lVar3 + 0x38);
    }
    if (((iVar1 != 0) && (*(long **)(lVar3 + 0x30) != (long *)0x0)) &&
       (uVar4 = (**(code **)(**(long **)(lVar3 + 0x30) + 0x38))(), (uVar4 & 1) != 0)) {
      lVar3 = FUN_022a3668(param_1 + 0x428);
      uVar5 = FUN_022a3668(param_1 + 0x428);
                    /* WARNING: Could not recover jumptable at 0x06eacf20. Too many branches */
                    /* WARNING: Treating indirect jump as call */
      (**(code **)(**(long **)(lVar3 + 0x30) + 0x60))(*(long **)(lVar3 + 0x30),uVar5);
      return;
    }
  }
  return;
}


```

## FUN_06f7bf40 @ `06f7bf40`

Reasons: caller of FUN_05c935ac at 06f7c144; caller of FUN_05c935ac at 06f7c1f0; caller of FUN_05c935ac at 06f7c560

```c

void FUN_06f7bf40(float param_1,long *param_2)

{
  byte bVar1;
  long lVar2;
  undefined1 auVar3 [16];
  undefined1 auVar4 [16];
  double dVar5;
  undefined *puVar6;
  bool bVar7;
  long lVar8;
  float *pfVar9;
  long lVar10;
  ulong uVar11;
  double *pdVar12;
  double *pdVar13;
  double dVar14;
  undefined1 auVar15 [16];
  float fVar19;
  undefined1 auVar16 [16];
  undefined1 auVar17 [16];
  undefined1 auVar18 [16];
  float fVar20;
  float fVar21;
  float fVar22;
  float fVar23;
  double dVar24;
  float fVar25;
  float fVar26;
  float fVar27;
  double dVar28;
  float fVar29;
  float fVar30;
  float fVar31;
  float fVar32;
  undefined8 uVar33;
  double dVar34;
  float fVar35;
  double dVar36;
  float fVar37;
  undefined8 uStack_98;
  float fStack_90;
  float fStack_8c;
  float fStack_74;
  float fStack_70;
  float fStack_6c;
  float fStack_68;
  float fStack_64;
  float fStack_60;
  long lStack_58;
  
  lVar2 = tpidr_el0;
  lStack_58 = *(long *)(lVar2 + 0x28);
  FUN_070233e4();
  if (*(float *)(param_2 + 0xcd) < 0.0) {
LAB_06f7bf84:
    bVar1 = *(byte *)((long)param_2 + 0x671);
  }
  else {
    param_1 = *(float *)(param_2 + 0xcd) + param_1;
    *(float *)(param_2 + 0xcd) = param_1;
    if (param_1 <= *(float *)((long)param_2 + 0x66c)) {
      lVar8 = FUN_06f7c6e0(param_2,*(long *)(param_2[0xa1] + 0x5b) + 0x29);
      param_2[0xcc] = lVar8;
      lVar8 = (**(code **)(*param_2 + 400))(param_2);
      lVar10 = param_2[0xcc];
      if (((lVar8 != 0) && (lVar10 != 0)) && ((char)param_2[0xce] != '\0')) {
        lVar8 = param_2[0xa3];
        if (lVar8 != 0) {
          lVar10 = FUN_05c935ac();
          if ((*(int *)(*(long *)(lVar8 + 0x10) + 0x38) < *(int *)(lVar10 + 0x38)) ||
             (*(long *)(*(long *)(*(long *)(lVar8 + 0x10) + 0x30) +
                       (long)*(int *)(lVar10 + 0x38) * 8) != lVar10 + 0x30)) {
            lVar10 = FUN_05de05bc();
            if ((*(int *)(lVar10 + 0x38) <= *(int *)(*(long *)(lVar8 + 0x10) + 0x38)) &&
               (*(long *)(*(long *)(*(long *)(lVar8 + 0x10) + 0x30) +
                         (long)*(int *)(lVar10 + 0x38) * 8) == lVar10 + 0x30)) {
              FUN_07034010(lVar8,0);
            }
          }
          else {
            FUN_07020bb0(lVar8,0);
          }
        }
        (**(code **)(*param_2 + 400))(param_2);
        FUN_0406e718(&fStack_90);
        fVar22 = fStack_8c;
        fVar20 = fStack_90;
        lVar8 = thunk_FUN_03ffa0e4(param_2[0xcc]);
        fVar25 = -fStack_70;
        fVar19 = -fStack_6c;
        fVar26 = 1.0 / (fStack_74 * fStack_68 - fStack_70 * fStack_6c);
        fVar21 = (float)*(undefined8 *)(lVar8 + 0x2c) +
                 (float)*(undefined8 *)(lVar8 + 0x1c) * (float)*(undefined8 *)PTR_DAT_0a118868 +
                 (float)*(undefined8 *)(lVar8 + 0x24) * *(float *)(PTR_DAT_0a118868 + 4);
        fVar23 = (float)((ulong)*(undefined8 *)(lVar8 + 0x2c) >> 0x20) +
                 (float)((ulong)*(undefined8 *)(lVar8 + 0x1c) >> 0x20) *
                 (float)*(undefined8 *)PTR_DAT_0a118868 +
                 (float)((ulong)*(undefined8 *)(lVar8 + 0x24) >> 0x20) *
                 *(float *)(PTR_DAT_0a118868 + 4);
        fVar30 = -fStack_60;
        fVar27 = fStack_74 * fVar26;
        fVar29 = fStack_68 * fVar26;
        uVar33 = NEON_rev64(CONCAT44(fVar23,fVar21),4);
        fVar31 = fVar25 * fVar26 * fStack_64;
        fVar32 = fVar29 * fStack_64;
        pfVar9 = (float *)FUN_03ff9c48(param_2[0xcc]);
        fVar37 = *pfVar9;
        fVar35 = pfVar9[1];
        lVar8 = param_2[0xa1];
        if ((param_2[0xa2] != 0) && (param_2[0xa2] != lVar8)) {
          FUN_06f7c8c4(param_2);
          lVar8 = param_2[0xa1];
          param_2[0xa2] = 0;
        }
        dVar5 = (double)(fVar21 * fVar25 * fVar26 + (float)uVar33 * fVar27 +
                        (fVar27 * fVar30 - fVar31));
        dVar24 = (double)(fVar23 * fVar19 * fVar26 + (float)((ulong)uVar33 >> 0x20) * fVar29 +
                         (fVar19 * fVar26 * fVar30 - fVar32));
        dVar34 = (double)fVar37;
        dVar36 = (double)fVar35;
        if (*(char *)(lVar8 + 0x5a) == '\x03') {
          lVar8 = *(long *)(lVar8 + 0x5b);
          if (lVar8 != 0) {
            dVar14 = *(double *)(lVar8 + 0x62);
            pdVar12 = (double *)(lVar8 + 0x6a);
            dVar28 = *(double *)(lVar8 + 0x52);
            pdVar13 = (double *)(lVar8 + 0x5a);
            goto LAB_06f7c444;
          }
        }
        else if ((*(char *)(lVar8 + 0x5a) == '\x02') &&
                (lVar8 = *(long *)(lVar8 + 0x5b), lVar8 != 0)) {
          dVar14 = *(double *)(lVar8 + 0x55);
          pdVar12 = (double *)(lVar8 + 0x5d);
          dVar28 = *(double *)(lVar8 + 0x45);
          pdVar13 = (double *)(lVar8 + 0x4d);
LAB_06f7c444:
          dVar34 = dVar14 + dVar34;
          dVar36 = *pdVar12 + dVar36;
          dVar5 = *pdVar13 + *pdVar12 * -0.5 + dVar5;
          dVar24 = dVar28 + dVar14 * -0.5 + dVar24;
        }
        auVar15._8_8_ = 0;
        auVar15._0_8_ = dVar24;
        FUN_06f7c9f0(auVar15,SUB84(dVar5,0),dVar34,dVar36,param_2);
        FUN_06f7c8c4(param_2,param_2[0xa1]);
        if ((char)param_2[0xa8] == '\x01') {
          auVar16._0_8_ = (double)fVar20;
          auVar16._8_8_ = 0;
          FUN_06f7cae0(auVar16,SUB84((double)fVar22,0),dVar24,dVar5,dVar34,dVar36,param_2);
          if (((*(int *)(*(long *)PTR_DAT_0a11eb10 + (ulong)(byte)*PTR_DAT_0a11eb30 * 0x7b0 + 0x7b0)
                == 1) && (uVar11 = FUN_022a3530(param_2 + 0xab), (uVar11 & 1) != 0)) &&
             (lVar8 = FUN_022a3668(param_2 + 0xab), *(char *)(lVar8 + 0x110) != '\0')) {
            FUN_022a3668(param_2 + 0xab);
            uVar11 = FUN_05f882ec();
            if ((uVar11 & 1) == 0) goto LAB_06f7c530;
          }
          FUN_05f4cb4c(param_2[0x9f],0,1,1);
        }
LAB_06f7c530:
        lVar10 = param_2[0xcc];
        *(undefined4 *)(param_2 + 0xcd) = 0xbf800000;
      }
      if (lVar10 != 0) {
        if ((*(byte *)(param_2 + 0xce) & 1) == 0) {
          lVar8 = param_2[0xa3];
          *(undefined1 *)(param_2 + 0xce) = 1;
          if (lVar8 != 0) {
            lVar10 = FUN_05c935ac();
            if ((*(int *)(*(long *)(lVar8 + 0x10) + 0x38) < *(int *)(lVar10 + 0x38)) ||
               (*(long *)(*(long *)(*(long *)(lVar8 + 0x10) + 0x30) +
                         (long)*(int *)(lVar10 + 0x38) * 8) != lVar10 + 0x30)) {
              lVar10 = FUN_05de05bc();
              if ((*(int *)(lVar10 + 0x38) <= *(int *)(*(long *)(lVar8 + 0x10) + 0x38)) &&
                 (*(long *)(*(long *)(*(long *)(lVar8 + 0x10) + 0x30) +
                           (long)*(int *)(lVar10 + 0x38) * 8) == lVar10 + 0x30)) {
                FUN_07034010(lVar8,1);
              }
            }
            else {
              FUN_07020bb0(lVar8,1);
            }
            param_2[0xa3] = 0;
          }
          param_2[0xcc] = 0;
          bVar1 = *(byte *)((long)param_2 + 0x671);
          goto joined_r0x06f7c28c;
        }
        *(undefined1 *)(param_2 + 0xce) = 0;
      }
      goto LAB_06f7bf84;
    }
    lVar8 = param_2[0xa3];
    if (lVar8 != 0) {
      lVar10 = FUN_05c935ac();
      if ((*(int *)(*(long *)(lVar8 + 0x10) + 0x38) < *(int *)(lVar10 + 0x38)) ||
         (*(long *)(*(long *)(*(long *)(lVar8 + 0x10) + 0x30) + (long)*(int *)(lVar10 + 0x38) * 8)
          != lVar10 + 0x30)) {
        lVar10 = FUN_05de05bc();
        if ((*(int *)(lVar10 + 0x38) <= *(int *)(*(long *)(lVar8 + 0x10) + 0x38)) &&
           (*(long *)(*(long *)(*(long *)(lVar8 + 0x10) + 0x30) + (long)*(int *)(lVar10 + 0x38) * 8)
            == lVar10 + 0x30)) {
          FUN_07034010(lVar8,1);
        }
      }
      else {
        FUN_07020bb0(lVar8,1);
      }
      param_2[0xa3] = 0;
    }
    puVar6 = PTR_DAT_0a11eb78;
    *(undefined1 *)(param_2 + 0xce) = 0;
    param_2[0xcc] = 0;
    uVar33 = *(undefined8 *)puVar6;
    *(undefined4 *)(param_2 + 0xcd) = 0xbf800000;
    FUN_068a6d0c(uVar33);
    bVar1 = *(byte *)((long)param_2 + 0x671);
  }
joined_r0x06f7c28c:
  if (((((bVar1 & 1) == 0) && ((double)param_2[0xd3] == 0.0)) || (param_2[0xcc] == 0)) ||
     (lVar8 = (**(code **)(*param_2 + 400))(param_2), lVar8 == 0)) goto LAB_06f7c68c;
  (**(code **)(*param_2 + 400))(param_2);
  FUN_0406e718(&fStack_90);
  lVar8 = thunk_FUN_03ffa0e4(param_2[0xcc]);
  fVar25 = 1.0 / (fStack_74 * fStack_68 - fStack_70 * fStack_6c);
  fVar20 = (float)*(undefined8 *)(lVar8 + 0x2c) +
           (float)*(undefined8 *)(lVar8 + 0x1c) * (float)*(undefined8 *)PTR_DAT_0a118868 +
           (float)*(undefined8 *)(lVar8 + 0x24) * *(float *)(PTR_DAT_0a118868 + 4);
  fVar22 = (float)((ulong)*(undefined8 *)(lVar8 + 0x2c) >> 0x20) +
           (float)((ulong)*(undefined8 *)(lVar8 + 0x1c) >> 0x20) *
           (float)*(undefined8 *)PTR_DAT_0a118868 +
           (float)((ulong)*(undefined8 *)(lVar8 + 0x24) >> 0x20) * *(float *)(PTR_DAT_0a118868 + 4);
  uVar33 = NEON_rev64(CONCAT44(fVar22,fVar20),4);
  fVar20 = fVar20 * -fStack_70 * fVar25 + (float)uVar33 * fStack_74 * fVar25 +
           (fStack_74 * fVar25 * -fStack_60 - -fStack_70 * fVar25 * fStack_64);
  fVar22 = fVar22 * -fStack_6c * fVar25 + (float)((ulong)uVar33 >> 0x20) * fStack_68 * fVar25 +
           (-fStack_6c * fVar25 * -fStack_60 - fStack_68 * fVar25 * fStack_64);
  pfVar9 = (float *)FUN_03ff9c48(param_2[0xcc]);
  if (((fVar22 == 0.0) && (fVar20 == 0.0)) || ((*pfVar9 == 0.0 && (pfVar9[1] == 0.0))))
  goto LAB_06f7c68c;
  dVar5 = (double)fVar20;
  dVar24 = (double)fVar22;
  dVar36 = (double)*pfVar9;
  dVar34 = (double)pfVar9[1];
  bVar7 = false;
  if (((double)param_2[0xcf] == dVar24) &&
     (bVar7 = false, !NAN((double)param_2[0xd0]) && !NAN(dVar5))) {
    bVar7 = (double)param_2[0xd0] == dVar5;
  }
  if ((((bVar7) && ((double)param_2[0xd1] == dVar36)) && ((double)param_2[0xd2] == dVar34)) &&
     (dVar14 = (double)param_2[0xd3], auVar15 = FUN_068a3d4c(*(undefined8 *)PTR_DAT_0a11eb08),
     dVar14 < auVar15._0_8_)) {
    param_2[0xd3] = 0;
    *(undefined1 *)((long)param_2 + 0x671) = 0;
    goto LAB_06f7c68c;
  }
  auVar3._8_8_ = dVar24;
  auVar3._0_8_ = dVar5;
  auVar4._8_8_ = dVar24;
  auVar4._0_8_ = dVar5;
  auVar15 = NEON_ext(auVar3,auVar4,8,1);
  lVar8 = param_2[0xa1];
  param_2[0xd1] = (long)dVar36;
  param_2[0xd2] = (long)dVar34;
  param_2[0xd0] = auVar15._8_8_;
  param_2[0xcf] = auVar15._0_8_;
  if (*(char *)(lVar8 + 0x5a) == '\x03') {
    lVar8 = *(long *)(lVar8 + 0x5b);
    if (lVar8 != 0) {
      dVar14 = *(double *)(lVar8 + 0x62);
      pdVar12 = (double *)(lVar8 + 0x6a);
      dVar28 = *(double *)(lVar8 + 0x52);
      pdVar13 = (double *)(lVar8 + 0x5a);
      goto LAB_06f7c5e8;
    }
  }
  else if ((*(char *)(lVar8 + 0x5a) == '\x02') && (lVar8 = *(long *)(lVar8 + 0x5b), lVar8 != 0)) {
    dVar14 = *(double *)(lVar8 + 0x55);
    pdVar12 = (double *)(lVar8 + 0x5d);
    dVar28 = *(double *)(lVar8 + 0x45);
    pdVar13 = (double *)(lVar8 + 0x4d);
LAB_06f7c5e8:
    dVar36 = dVar14 + dVar36;
    dVar34 = *pdVar12 + dVar34;
    dVar5 = *pdVar13 + *pdVar12 * -0.5 + dVar5;
    dVar24 = dVar28 + dVar14 * -0.5 + dVar24;
  }
  auVar17._8_8_ = 0;
  auVar17._0_8_ = dVar24;
  FUN_06f7c9f0(auVar17,SUB84(dVar5,0),dVar36,dVar34,param_2);
  if ((char)param_2[0xa8] == '\x01') {
    auVar18._0_8_ = (double)fStack_90;
    auVar18._8_8_ = 0;
    FUN_06f7cae0(auVar18,SUB84((double)fStack_8c,0),dVar24,dVar5,dVar36,dVar34,param_2);
  }
  uVar11 = FUN_022a3530(param_2 + 0xab);
  if ((uVar11 & 1) != 0) {
    uVar33 = FUN_022a3668(param_2 + 0xab);
    uStack_98 = 0;
    FUN_022a3430(&uStack_98,param_2[0xcc]);
    FUN_05f94e58(uVar33,uStack_98);
  }
LAB_06f7c68c:
  if (*(long *)(lVar2 + 0x28) == lStack_58) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_06f7f5b4 @ `06f7f5b4`

Reasons: caller of FUN_05c935ac at 06f7f5fc

```c

void FUN_06f7f5b4(long param_1,long param_2)

{
  uint uVar1;
  long lVar2;
  int iVar3;
  long lVar4;
  undefined8 uVar5;
  long *plVar6;
  ulong uVar7;
  long lVar8;
  uint uVar9;
  long lStack_70;
  long lStack_68;
  long *plStack_60;
  long lStack_58;
  
  lVar2 = tpidr_el0;
  lVar4 = 0;
  lStack_58 = *(long *)(lVar2 + 0x28);
  if ((param_2 == 0) || (*(int *)(*(long *)(*(long *)(param_1 + 0x508) + 0x5b) + 0x39) == 0))
  goto LAB_06f7f658;
  lVar4 = FUN_05c935ac(0);
  if ((*(int *)(*(long *)(param_2 + 0x10) + 0x38) < *(int *)(lVar4 + 0x38)) ||
     (*(long *)(*(long *)(*(long *)(param_2 + 0x10) + 0x30) + (long)*(int *)(lVar4 + 0x38) * 8) !=
      lVar4 + 0x30)) {
    lVar4 = FUN_05de05bc();
    if ((*(int *)(lVar4 + 0x38) <= *(int *)(*(long *)(param_2 + 0x10) + 0x38)) &&
       (*(long *)(*(long *)(*(long *)(param_2 + 0x10) + 0x30) + (long)*(int *)(lVar4 + 0x38) * 8) ==
        lVar4 + 0x30)) {
      uVar1 = *(uint *)(param_2 + 0xb40);
      iVar3 = *(int *)(*(long *)(*(long *)(param_1 + 0x508) + 0x5b) + 0x39);
      if ((iVar3 == 0) || (*(int *)(*(long *)(lRam000000000a401370 + 0x2e0) + 0x2fa8) < iVar3)) {
        if (0 < (int)uVar1) {
          uVar7 = 0;
          do {
            if (((long)uVar7 < (long)*(int *)(param_2 + 0xb40)) &&
               (lVar8 = *(long *)(*(long *)(param_2 + 0xb38) + uVar7 * 8), lVar8 != 0)) {
              uVar5 = FUN_05de7f10(lVar4);
              plVar6 = (long *)FUN_0227b8d0(lVar8,uVar5);
              if ((plVar6 != (long *)0x0) &&
                 (lVar4 = (**(code **)(*plVar6 + 0x18))(), lVar4 == iVar3)) {
                FUN_03fb7238(param_2,uVar7 & 0xffffffff);
                lStack_70 = lVar8;
                plVar6 = (long *)(**(code **)(*(long *)(param_2 + 0x298) + 0x58))(param_2 + 0x298);
                if (plVar6 != (long *)0x0) goto LAB_06f7f80c;
                lVar4 = 0;
                break;
              }
            }
            uVar7 = uVar7 + 1;
            lVar4 = 0;
          } while (uVar1 != uVar7);
          goto LAB_06f7f658;
        }
      }
      else {
        lVar4 = 0;
        if ((iVar3 < 1) || ((int)uVar1 < iVar3)) goto LAB_06f7f658;
        lVar4 = *(long *)(*(long *)(param_2 + 0xb38) + (ulong)(iVar3 - 1) * 8);
        if (lVar4 != 0) {
          FUN_03fb7238(param_2);
          lVar4 = FUN_06c02034(param_2,lVar4);
          if (lVar4 == 0) goto LAB_06f7f658;
          uVar7 = FUN_03ffb8ec();
          if ((uVar7 & 1) != 0) {
            *(long *)(param_1 + 0x518) = param_2;
            goto LAB_06f7f658;
          }
        }
      }
    }
  }
  else {
    uVar1 = *(uint *)(param_2 + 0xb40);
    iVar3 = *(int *)(*(long *)(*(long *)(param_1 + 0x508) + 0x5b) + 0x39);
    if ((iVar3 == 0) || (*(int *)(*(long *)(lRam000000000a401370 + 0x2e0) + 0x2fa8) < iVar3)) {
      if (0 < (int)uVar1) {
        uVar7 = 0;
        do {
          if (((long)uVar7 < (long)*(int *)(param_2 + 0xb40)) &&
             (lVar4 = *(long *)(*(long *)(param_2 + 0xb38) + uVar7 * 8), lVar4 != 0)) {
            uVar5 = FUN_05de7f10();
            plVar6 = (long *)FUN_0227b8d0(lVar4,uVar5);
            if ((plVar6 != (long *)0x0) && (lVar8 = (**(code **)(*plVar6 + 0x18))(), lVar8 == iVar3)
               ) {
              uVar9 = (uint)uVar7;
              goto LAB_06f7f7ec;
            }
          }
          uVar7 = uVar7 + 1;
        } while (uVar1 != uVar7);
      }
    }
    else {
      uVar9 = iVar3 - 1;
      lVar4 = 0;
      if ((iVar3 < 1) || ((int)uVar1 < iVar3)) goto LAB_06f7f658;
      lVar4 = *(long *)(*(long *)(param_2 + 0xb38) + (ulong)uVar9 * 8);
      if (lVar4 != 0) {
LAB_06f7f7ec:
        FUN_03fba800((float)(int)uVar9,param_2);
        lStack_70 = lVar4;
        plVar6 = (long *)(**(code **)(*(long *)(param_2 + 0x298) + 0x58))(param_2 + 0x298);
        lVar4 = 0;
        if (plVar6 == (long *)0x0) goto LAB_06f7f658;
LAB_06f7f80c:
        (**(code **)(*plVar6 + 0x3d8))(&lStack_68,plVar6,&lStack_70);
        plVar6 = plStack_60;
        if (((plStack_60 != (long *)0x0) &&
            (FUN_08d08290(1,plStack_60 + 1), plStack_60 != (long *)0x0)) &&
           (iVar3 = FUN_08d08320(0xffffffff,plStack_60 + 1), iVar3 == 1)) {
          (**(code **)*plStack_60)(plStack_60);
          iVar3 = FUN_08d08320(0xffffffff,(long)plStack_60 + 0xc);
          if (iVar3 == 1) {
            (**(code **)(*plStack_60 + 0x10))(plStack_60);
          }
        }
        if (lStack_68 == 0) {
          lVar4 = 0;
        }
        else {
          lVar4 = *(long *)(lStack_68 + -8);
        }
        if ((plVar6 != (long *)0x0) && (iVar3 = FUN_08d08320(0xffffffff,plVar6 + 1), iVar3 == 1)) {
          (**(code **)*plVar6)(plVar6);
          iVar3 = FUN_08d08320(0xffffffff,(long)plVar6 + 0xc);
          if (iVar3 == 1) {
            (**(code **)(*plVar6 + 0x10))(plVar6);
          }
        }
        if (lVar4 == 0) goto LAB_06f7f658;
        uVar7 = FUN_03ffb8ec(lVar4);
        if ((uVar7 & 1) != 0) {
          *(long *)(param_1 + 0x518) = param_2;
          goto LAB_06f7f658;
        }
      }
    }
  }
  lVar4 = 0;
LAB_06f7f658:
  if (*(long *)(lVar2 + 0x28) != lStack_58) {
                    /* WARNING: Subroutine does not return */
    __stack_chk_fail(lVar4);
  }
  return;
}


```

## FUN_06fb5b34 @ `06fb5b34`

Reasons: caller of FUN_05c935ac at 06fb5b54

```c

void FUN_06fb5b34(long param_1)

{
  long lVar1;
  long lVar2;
  undefined8 uStack_30;
  long lStack_28;
  
  lVar1 = FUN_03f2a9d4(param_1 + -8);
  if (lVar1 != 0) {
    lVar2 = FUN_05c935ac();
    if ((*(int *)(lVar2 + 0x38) <= *(int *)(*(long *)(lVar1 + 0x10) + 0x38)) &&
       (*(long *)(*(long *)(*(long *)(lVar1 + 0x10) + 0x30) + (long)*(int *)(lVar2 + 0x38) * 8) ==
        lVar2 + 0x30)) {
      uStack_30 = FUN_03f2b638(param_1 + -8);
      lVar2 = tpidr_el0;
      lStack_28 = *(long *)(lVar2 + 0x28);
      FUN_03fb8da4(lVar1 + 0x298,&uStack_30,3);
      if (*(long *)(lVar2 + 0x28) == lStack_28) {
        return;
      }
                    /* WARNING: Subroutine does not return */
      __stack_chk_fail();
    }
  }
  return;
}


```

## FUN_05bdfcec @ `05bdfcec`

Reasons: RFExchangeBuySlot metadata

```c

void FUN_05bdfcec(undefined8 *param_1)

{
  undefined8 *puVar1;
  
  puVar1 = (undefined8 *)*param_1;
  FUN_05e02170(puVar1,param_1);
  puVar1[0x7e] = 0;
  *puVar1 = &UNK_09796cb8;
  puVar1[5] = &UNK_09797228;
  puVar1[0x2f] = &UNK_09797280;
  puVar1[0x5c] = &UNK_097972c0;
  puVar1[0x78] = &UNK_09797300;
  puVar1[0x80] = 0;
  puVar1[0x7f] = 0;
  return;
}


```

## FUN_05be0dd0 @ `05be0dd0`

Reasons: RFExchangeItemSlot metadata

```c

void FUN_05be0dd0(undefined8 *param_1)

{
  undefined8 *puVar1;
  
  puVar1 = (undefined8 *)*param_1;
  FUN_05e02170(puVar1,param_1);
  *puVar1 = &UNK_09798478;
  puVar1[5] = &UNK_097989e0;
  puVar1[0x5c] = &UNK_09798a78;
  puVar1[0x2f] = &UNK_09798a38;
  *(undefined4 *)(puVar1 + 0x8a) = 2;
  puVar1[0x84] = 0;
  puVar1[0x83] = 0;
  puVar1[0x87] = 0;
  puVar1[0x86] = 0;
  puVar1[0x89] = 0;
  puVar1[0x88] = 0;
  *(undefined8 *)((long)puVar1 + 0x45c) = 0;
  *(undefined8 *)((long)puVar1 + 0x454) = 0;
  *(undefined4 *)((long)puVar1 + 0x464) = 0;
  return;
}


```

## FUN_05be195c @ `05be195c`

Reasons: RFExchangeSellSlot metadata

```c

void FUN_05be195c(undefined8 *param_1)

{
  undefined8 *puVar1;
  
  puVar1 = (undefined8 *)*param_1;
  FUN_05e02170(puVar1,param_1);
  *puVar1 = &UNK_09799e60;
  puVar1[5] = &UNK_0979a3d0;
  puVar1[0x2f] = &UNK_0979a428;
  puVar1[0x5c] = &UNK_0979a468;
  puVar1[0x78] = &UNK_0979a4a8;
  return;
}


```

## FUN_05be21c8 @ `05be21c8`

Reasons: RFExchangeTransactionSlot metadata

```c

void FUN_05be21c8(undefined8 *param_1)

{
  undefined8 *puVar1;
  
  puVar1 = (undefined8 *)*param_1;
  FUN_05e02170(puVar1,param_1);
  *puVar1 = &UNK_0979c850;
  puVar1[5] = &UNK_0979cdc0;
  puVar1[0x2f] = &UNK_0979ce18;
  puVar1[0x5c] = &UNK_0979ce58;
  puVar1[0x78] = &UNK_0979ce98;
  return;
}


```

## FUN_05cedcb8 @ `05cedcb8`

Reasons: RFPanelExchangeMain metadata

```c

void FUN_05cedcb8(undefined8 *param_1)

{
  undefined8 *puVar1;
  
  puVar1 = (undefined8 *)*param_1;
  FUN_05cda240(puVar1,param_1);
  *puVar1 = &UNK_09965368;
  puVar1[5] = &UNK_09965978;
  puVar1[0x2f] = &UNK_099659d0;
  puVar1[0x5c] = &UNK_09965a10;
  puVar1[0x91] = 0;
  puVar1[0x90] = 0;
  puVar1[0x93] = 0;
  puVar1[0x92] = 0;
  puVar1[0x94] = 0;
  FUN_01ec3800(puVar1 + 0x93,0);
  puVar1[0x99] = 0;
  puVar1[0x96] = 0;
  puVar1[0x95] = 0;
  puVar1[0x98] = 0;
  puVar1[0x97] = 0;
  FUN_01ec3800(puVar1 + 0x98,0);
  *(undefined2 *)(puVar1 + 0x10b) = 0;
  puVar1[0x10c] = 0;
  puVar1[0xac] = 0;
  puVar1[0xab] = 0;
  *(undefined2 *)(puVar1 + 0x103) = 9999;
  *(undefined2 *)((long)puVar1 + 0x823) = 0;
  puVar1[0xc6] = 0;
  puVar1[0xc5] = 0;
  puVar1[200] = 0;
  puVar1[199] = 0;
  puVar1[0x106] = 0;
  puVar1[0x105] = 0;
  puVar1[0xa1] = 0;
  puVar1[0xa0] = 0;
  puVar1[0x10a] = 0;
  puVar1[0x109] = 0;
  puVar1[0x10e] = 0;
  puVar1[0x10d] = 0;
  *(undefined1 *)(puVar1 + 0x10f) = 0;
  FUN_01ec2f94(puVar1 + 0x110,&UNK_0065d83a);
  puVar1[0x11b] = 0;
  *(undefined2 *)(puVar1 + 0x112) = 0;
  puVar1[0x11f] = 0;
  *(undefined4 *)(puVar1 + 0x120) = 0;
  puVar1[0x114] = 0;
  puVar1[0x113] = 0;
  puVar1[0x116] = 0;
  puVar1[0x115] = 0;
  puVar1[0x118] = 0;
  puVar1[0x117] = 0;
  puVar1[0x11c] = 0x8000000000;
  *(undefined2 *)(puVar1 + 0x121) = 0x101;
  *(undefined1 *)((long)puVar1 + 0x90a) = 1;
  puVar1[0x11d] = 0xffffffff;
  *(undefined4 *)((long)puVar1 + 0x90c) = 2;
  return;
}


```

## Run summary

- Decompiled functions: 21
- Candidate functions: 21
- Cancelled: false
