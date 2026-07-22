# RF Online NEXT - selected string xrefs

Generated: 2026-07-21T12:00:49.876753300Z

- Program: `libUnreal.so`
- Image base: `00100000`
- Candidate functions: 20

## String occurrences and references

### `OnUpdateAuctionProductInfo`

- Occurrence: `0072ad76`
- No direct Ghidra reference found.

### `OnUpdateRegsterAuctionItemList`

- Occurrence: `006ad04b`
- No direct Ghidra reference found.

### `OnOpenAuctionItemList`

- Occurrence: `006ad06a`
- Occurrence: `001bfd88`
- Reference: `adrp+add 06c0de6c -> 06c0de70 FUN_06c0c370 @ 06c0c370`

### `TradeItemList`

- Occurrence: `006ad0ad`
- No direct Ghidra reference found.

### `ExchangePriceInfoSlotArr`

- Occurrence: `00701bb2`
- No direct Ghidra reference found.

### `ERFExchangePriceType::CurrentLowest`

- Occurrence: `006ae2b3`
- No direct Ghidra reference found.

### `ERFExchangePriceType::SellLowestPrice`

- Occurrence: `007d4f5e`
- No direct Ghidra reference found.

### `ERFExchangePriceType::LastPrice`

- Occurrence: `007d4f99`
- No direct Ghidra reference found.

### `ERFExchangePriceType::SellPrice`

- Occurrence: `007d5036`
- No direct Ghidra reference found.

### `ERFExchangePriceType::PurchasePrice`

- Occurrence: `007d5061`
- No direct Ghidra reference found.

### `ERFExchangePriceType::TotalSellPrice`

- Occurrence: `007d5011`
- No direct Ghidra reference found.

### `ERFExchangePriceType::CurrentHighest`

- Occurrence: `006af1f5`
- No direct Ghidra reference found.

### `WGExchangeItem`

- Occurrence: `00752391`
- No direct Ghidra reference found.

### `Handle_FL2C_noti_mapcontent_guild_auction_reward_list_Message`

- Occurrence: `007c511a`
- Reference: `adrp+add 06078014 -> 06078018 FUN_06077dac @ 06077dac`

### `RFPanelExchangeMain`

- Occurrence: `003145c4`
- Reference: `adrp+add 05cedb88 -> 05cedb8c FUN_05cedb10 @ 05cedb10`
- Reference: `adrp+add 05cedc64 -> 05cedc68 FUN_05cedbec @ 05cedbec`

### `RFExchangeBuySlot`

- Occurrence: `001c7efc`
- Reference: `adrp+add 05bdfbbc -> 05bdfbc0 FUN_05bdfb44 @ 05bdfb44`
- Reference: `adrp+add 05bdfc98 -> 05bdfc9c FUN_05bdfc20 @ 05bdfc20`

### `RFExchangeBuyGroupSlot`

- Occurrence: `001c91b4`
- Reference: `adrp+add 05bde540 -> 05bde544 FUN_05bde4c8 @ 05bde4c8`
- Reference: `adrp+add 05bde61c -> 05bde620 FUN_05bde5a4 @ 05bde5a4`

### `RFExchangeItemSlot`

- Occurrence: `006855b0`
- Occurrence: `0069662a`
- Occurrence: `006c2371`
- Occurrence: `00717db8`
- Occurrence: `007a2151`
- Occurrence: `001c9b90`
- Occurrence: `003ce958`
- Reference: `adrp+add 05be0ca0 -> 05be0ca4 FUN_05be0c28 @ 05be0c28`
- Reference: `adrp+add 05be0d7c -> 05be0d80 FUN_05be0d04 @ 05be0d04`

### `RFExchangeSellSlot`

- Occurrence: `001c9d3e`
- Reference: `adrp+add 05be182c -> 05be1830 FUN_05be17b4 @ 05be17b4`
- Reference: `adrp+add 05be1908 -> 05be190c FUN_05be1890 @ 05be1890`

### `RFExchangeTransactionSlot`

- Occurrence: `001c9804`
- Reference: `adrp+add 05be2294 -> 05be2298 FUN_05be221c @ 05be221c`

### `WBP_Exchange_Buy_Slot_C`

- No occurrence found.

### `WBP_Exchange_Main_C`

- No occurrence found.

### `WBP_Exchange_Sell_Slot_C`

- No occurrence found.

### `LV_Buy_List`

- Occurrence: `006add89`
- No direct Ghidra reference found.

### `LV_BuyGroup_List`

- Occurrence: `006adde4`
- No direct Ghidra reference found.

### `LV_Sell_List`

- Occurrence: `006adec9`
- No direct Ghidra reference found.

### `LV_Transaction_List`

- Occurrence: `006ade58`
- No direct Ghidra reference found.

### `RequestPurchaseListForLog`

- Occurrence: `00770c2f`
- No direct Ghidra reference found.

## FUN_05bde4c8 @ `05bde4c8`

Reasons: ADRP+ADD resolves RFExchangeBuyGroupSlot @ 001c91b4

```c

void FUN_05bde4c8(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a423b00 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c91b4,0xa423b00,FUN_05bde4c8,0x3f0,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05bde670,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  FUN_021325f0(lRam000000000a423b00,&UNK_09794608,2);
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_05bde5a4 @ `05bde5a4`

Reasons: ADRP+ADD resolves RFExchangeBuyGroupSlot @ 001c91b4

```c

void FUN_05bde5a4(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a423b00 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c91b4,0xa423b00,FUN_05bde4c8,0x3f0,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05bde670,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail(lRam000000000a423b00);
}


```

## FUN_05bdfb44 @ `05bdfb44`

Reasons: ADRP+ADD resolves RFExchangeBuySlot @ 001c7efc

```c

void FUN_05bdfb44(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a423ba0 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c7efc,0xa423ba0,FUN_05bdfb44,0x408,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05bdfcec,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  FUN_021325f0(lRam000000000a423ba0,&UNK_09796a58,2);
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_05bdfc20 @ `05bdfc20`

Reasons: ADRP+ADD resolves RFExchangeBuySlot @ 001c7efc

```c

void FUN_05bdfc20(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a423ba0 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c7efc,0xa423ba0,FUN_05bdfb44,0x408,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05bdfcec,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail(lRam000000000a423ba0);
}


```

## FUN_05be0c28 @ `05be0c28`

Reasons: ADRP+ADD resolves RFExchangeItemSlot @ 001c9b90

```c

void FUN_05be0c28(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a4248b0 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c9b90,0xa4248b0,FUN_05be0c28,0x468,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05be0dd0,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  FUN_021325f0(lRam000000000a4248b0,&UNK_09798178,3);
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_05be0d04 @ `05be0d04`

Reasons: ADRP+ADD resolves RFExchangeItemSlot @ 001c9b90

```c

void FUN_05be0d04(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a4248b0 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c9b90,0xa4248b0,FUN_05be0c28,0x468,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05be0dd0,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail(lRam000000000a4248b0);
}


```

## FUN_05be17b4 @ `05be17b4`

Reasons: ADRP+ADD resolves RFExchangeSellSlot @ 001c9d3e

```c

void FUN_05be17b4(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a424940 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c9d3e,0xa424940,FUN_05be17b4,0x458,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05be195c,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  FUN_021325f0(lRam000000000a424940,&UNK_097999b0,7);
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_05be1890 @ `05be1890`

Reasons: ADRP+ADD resolves RFExchangeSellSlot @ 001c9d3e

```c

void FUN_05be1890(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a424940 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c9d3e,0xa424940,FUN_05be17b4,0x458,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05be195c,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail(lRam000000000a424940);
}


```

## FUN_05be221c @ `05be221c`

Reasons: ADRP+ADD resolves RFExchangeTransactionSlot @ 001c9804

```c

void FUN_05be221c(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a4249c8 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_001c9804,0xa4249c8,
                 Java_com_epicgames_unreal_NativeCalls_ForwardNotification,0x400,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05be21c8,FUN_01e9f210,&puStack_30,thunk_FUN_05e01f7c,FUN_020be9ec
                );
  }
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail(lRam000000000a4249c8);
}


```

## FUN_05cedb10 @ `05cedb10`

Reasons: ADRP+ADD resolves RFPanelExchangeMain @ 003145c4

```c

void FUN_05cedb10(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a448b78 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_003145c4,0xa448b78,FUN_05cedb10,0x910,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05cedcb8,FUN_01e9f210,&puStack_30,thunk_FUN_05cdb810,FUN_020be9ec
                );
  }
  FUN_021325f0(lRam000000000a448b78,&UNK_09963050,0x24);
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_05cedbec @ `05cedbec`

Reasons: ADRP+ADD resolves RFPanelExchangeMain @ 003145c4

```c

void FUN_05cedbec(void)

{
  long lVar1;
  undefined *puStack_30;
  long lStack_28;
  
  lVar1 = tpidr_el0;
  lStack_28 = *(long *)(lVar1 + 0x28);
  if (lRam000000000a448b78 == 0) {
    puStack_30 = PTR_Java_com_epicgames_unreal_NativeCalls_ForwardNotification_0a118f78;
    FUN_02132c44(&UNK_004acc10,&UNK_003145c4,0xa448b78,FUN_05cedb10,0x910,8,0x10000000,0,
                 &UNK_003d5a06,FUN_05cedcb8,FUN_01e9f210,&puStack_30,thunk_FUN_05cdb810,FUN_020be9ec
                );
  }
  if (*(long *)(lVar1 + 0x28) == lStack_28) {
    return;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail(lRam000000000a448b78);
}


```

## FUN_064e6e88 @ `064e6e88`

Reasons: caller of FUN_05cedbec at 064e6eb4; caller of FUN_05cedbec at 064e6f5c

```c

long FUN_064e6e88(long param_1,long param_2,ulong param_3)

{
  long lVar1;
  long lVar2;
  ulong uVar3;
  long *plVar4;
  long lVar5;
  long *plStack_48;
  undefined8 uStack_40;
  long lStack_38;
  
  lVar1 = tpidr_el0;
  lStack_38 = *(long *)(lVar1 + 0x28);
  if (param_2 == 0) {
    lVar2 = FUN_05cedbec();
    param_2 = *(long *)(lVar2 + 0x18);
  }
  plStack_48 = (long *)0x0;
  uStack_40 = 0;
  FUN_02f5712c(param_1 + 0x78,param_2,&plStack_48,0);
  if ((int)uStack_40 == 0) {
    lVar2 = 0;
  }
  else {
    plVar4 = plStack_48;
    if ((param_3 & 1) == 0) {
      lVar5 = (long)(int)uStack_40 << 3;
      do {
        if ((*plVar4 != 0) && (uVar3 = FUN_07024dac(), (uVar3 & 1) == 0)) {
          uVar3 = (**(code **)(*(long *)*plVar4 + 0x598))();
          if ((uVar3 & 1) != 0) goto LAB_064e6f54;
          lVar2 = 0;
          break;
        }
        lVar5 = lVar5 + -8;
        plVar4 = plVar4 + 1;
        lVar2 = 0;
      } while (lVar5 != 0);
    }
    else {
      lVar5 = (long)(int)uStack_40 << 3;
      do {
        if (((long *)*plVar4 != (long *)0x0) &&
           (uVar3 = (**(code **)(*(long *)*plVar4 + 0x598))(), (uVar3 & 1) != 0)) goto LAB_064e6f54;
        lVar5 = lVar5 + -8;
        plVar4 = plVar4 + 1;
        lVar2 = 0;
      } while (lVar5 != 0);
    }
  }
joined_r0x064e6fcc:
  if (plStack_48 != (long *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4(plStack_48);
  }
  if (*(long *)(lVar1 + 0x28) == lStack_38) {
    return lVar2;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
LAB_064e6f54:
  lVar2 = *plVar4;
  if (lVar2 != 0) {
    lVar5 = FUN_05cedbec();
    if ((*(int *)(lVar5 + 0x38) <= *(int *)(*(long *)(lVar2 + 0x10) + 0x38)) &&
       (*(long *)(*(long *)(*(long *)(lVar2 + 0x10) + 0x30) + (long)*(int *)(lVar5 + 0x38) * 8) ==
        lVar5 + 0x30)) goto joined_r0x064e6fcc;
  }
  lVar2 = 0;
  goto joined_r0x064e6fcc;
}


```

## FUN_06796ec0 @ `06796ec0`

Reasons: caller of FUN_05cedbec at 06796f20; caller of FUN_05cedbec at 06796fb0

```c

long FUN_06796ec0(long *param_1,undefined4 param_2,undefined4 param_3,undefined4 param_4,
                 long param_5,uint param_6,undefined8 param_7,uint param_8)

{
  long lVar1;
  long lVar2;
  long lVar3;
  undefined8 *puStack_78;
  int iStack_70;
  long lStack_68;
  
  lVar1 = tpidr_el0;
  lStack_68 = *(long *)(lVar1 + 0x28);
  lVar2 = (**(code **)(*param_1 + 400))();
  if (lVar2 != 0) {
    if (param_5 == 0) {
      lVar2 = FUN_05cedbec();
      param_5 = *(long *)(lVar2 + 0x18);
    }
    puStack_78 = (undefined8 *)0x0;
    iStack_70 = 0;
    FUN_01eac93c(&puStack_78,param_7);
    lVar2 = FUN_06814368(param_1,param_2,param_3,param_4,param_5,param_6 & 1,&puStack_78,param_8 & 1
                         ,1);
    if (iStack_70 == 0) {
LAB_06796fa0:
      if (puStack_78 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
        FUN_01f18da4();
      }
    }
    else if (puStack_78 != (undefined8 *)0x0) {
      (**(code **)*puStack_78)();
      FUN_01ec217c(&puStack_78,0,0,0x10);
      iStack_70 = 0;
      goto LAB_06796fa0;
    }
    if (lVar2 != 0) {
      lVar3 = FUN_05cedbec();
      if ((*(int *)(lVar3 + 0x38) <= *(int *)(*(long *)(lVar2 + 0x10) + 0x38)) &&
         (*(long *)(*(long *)(*(long *)(lVar2 + 0x10) + 0x30) + (long)*(int *)(lVar3 + 0x38) * 8) ==
          lVar3 + 0x30)) goto LAB_06796fe0;
    }
  }
  lVar2 = 0;
LAB_06796fe0:
  if (*(long *)(lVar1 + 0x28) == lStack_68) {
    return lVar2;
  }
                    /* WARNING: Subroutine does not return */
  __stack_chk_fail();
}


```

## FUN_06077dac @ `06077dac`

Reasons: ADRP+ADD resolves Handle_FL2C_noti_mapcontent_guild_auction_reward_list_Message @ 007c511a

```c

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

undefined8 FUN_06077dac(long *param_1)

{
  undefined *puVar1;
  uint uVar2;
  long lVar3;
  ulong uVar4;
  undefined8 uVar5;
  int iVar6;
  long *plVar7;
  long lVar8;
  long alStack_100 [2];
  undefined1 auStack_f0 [8];
  long lStack_e8;
  undefined8 uStack_e0;
  long alStack_d8 [2];
  long lStack_c8;
  int iStack_c0;
  undefined *puStack_b8;
  int iStack_b0;
  long alStack_a8 [2];
  long lStack_98;
  undefined1 auStack_88 [16];
  long lStack_78;
  long lStack_68;
  
  lVar3 = tpidr_el0;
  lStack_68 = *(long *)(lVar3 + 0x28);
  uVar4 = (**(code **)(*param_1 + 0x48))();
  if ((uVar4 & 1) != 0) {
    lVar8 = param_1[1];
    uVar5 = FUN_05ca8b04();
    FUN_0216bb7c(alStack_d8,uVar5,(char)lVar8);
    FUN_0203a370(alStack_a8,alStack_d8);
    lStack_c8 = 0;
    iStack_c0 = 1;
    FUN_01fbf650(&lStack_c8,1,0);
    *(undefined8 *)(lStack_c8 + 0x10) = 0;
    *(undefined8 *)(lStack_c8 + 0x18) = 0;
    FUN_0203a3c8(lStack_c8,alStack_a8);
    FUN_0203c1a8(&puStack_b8,&UNK_005e45b2,&lStack_c8);
    if (iStack_c0 != 0) {
      plVar7 = (long *)(lStack_c8 + 0x10);
      iVar6 = iStack_c0;
      do {
        if (*plVar7 != 0) {
                    /* WARNING: Subroutine does not return */
          FUN_01f18da4();
        }
        iVar6 = iVar6 + -1;
        plVar7 = plVar7 + 4;
      } while (iVar6 != 0);
    }
    if (lStack_c8 != 0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    if (lStack_98 != 0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    if (alStack_d8[0] != 0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    uVar2 = *(uint *)(param_1 + 3);
    if (0 < (int)uVar2) {
      uVar4 = 0;
      do {
        lVar8 = param_1[2] + uVar4 * 0x28;
        FUN_0203a308(alStack_a8,*(undefined4 *)(lVar8 + 4));
        FUN_0203a320(auStack_88,*(undefined8 *)(lVar8 + 8));
        lStack_e8 = 0;
        uStack_e0 = CONCAT44(uStack_e0._4_4_,2);
        FUN_01fbf650(&lStack_e8,2,0);
        lVar8 = lStack_e8;
        *(undefined8 *)(lStack_e8 + 0x10) = 0;
        *(undefined8 *)(lStack_e8 + 0x18) = 0;
        FUN_0203a3c8(lStack_e8,alStack_a8);
        *(undefined8 *)(lVar8 + 0x30) = 0;
        *(undefined8 *)(lVar8 + 0x38) = 0;
        FUN_0203a3c8(lVar8 + 0x20,auStack_88);
        FUN_0203c1a8(&lStack_c8,&UNK_005e463c,&lStack_e8);
        iVar6 = 0;
        if (iStack_c0 != 0) {
          iVar6 = iStack_c0 + -1;
        }
        thunk_FUN_01ec3a50(&puStack_b8,lStack_c8,iVar6);
        if (lStack_c8 != 0) {
                    /* WARNING: Subroutine does not return */
          FUN_01f18da4();
        }
        if ((int)uStack_e0 != 0) {
          plVar7 = (long *)(lStack_e8 + 0x10);
          iVar6 = (int)uStack_e0;
          do {
            if (*plVar7 != 0) {
                    /* WARNING: Subroutine does not return */
              FUN_01f18da4();
            }
            iVar6 = iVar6 + -1;
            plVar7 = plVar7 + 4;
          } while (iVar6 != 0);
        }
        if (lStack_e8 != 0) {
                    /* WARNING: Subroutine does not return */
          FUN_01f18da4();
        }
        if (lStack_78 != 0) {
                    /* WARNING: Subroutine does not return */
          FUN_01f18da4();
        }
        if (lStack_98 != 0) {
                    /* WARNING: Subroutine does not return */
          FUN_01f18da4();
        }
        uVar4 = uVar4 + 1;
      } while (uVar4 != uVar2);
    }
    FUN_0206e308(auStack_f0,&UNK_00431a20,1);
    puVar1 = &UNK_0065d83a;
    if (iStack_b0 != 0) {
      puVar1 = puStack_b8;
    }
    FUN_01ec2f94(alStack_a8,puVar1);
    FUN_01ec2e28(&lStack_c8,&UNK_0072e4d1);
    lStack_e8 = 0;
    uStack_e0 = 0;
    FUN_01ec6dd4(&lStack_e8,0xe8);
    FUN_01ec2e28(alStack_100,&UNK_007c511a);
    FUN_05f078c4(auStack_f0,alStack_a8,&lStack_c8,&lStack_e8,alStack_100);
    if (alStack_100[0] != 0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    if (lStack_e8 != 0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    if (lStack_c8 != 0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    if (alStack_a8[0] != 0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    if (puStack_b8 != (undefined *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    if ((char)param_1[1] == '\x04') {
      uVar5 = FUN_05ed55f8(*(undefined8 *)(_DAT_0a4a4428 + 0x3860));
      FUN_0645bda0(uVar5,param_1);
    }
    else if ((char)param_1[1] == '\v') {
      uVar5 = FUN_0603e4b8(*(undefined8 *)(_DAT_0a4a4428 + 0x3860));
      FUN_06694b98(uVar5,param_1);
    }
  }
  if (*(long *)(lVar3 + 0x28) != lStack_68) {
                    /* WARNING: Subroutine does not return */
    __stack_chk_fail();
  }
  return 1;
}


```

## FUN_06c0c370 @ `06c0c370`

Reasons: ADRP+ADD resolves OnOpenAuctionItemList @ 001bfd88

```c

/* WARNING: Globals starting with '_' overlap smaller symbols at the same address */

void FUN_06c0c370(long param_1)

{
  undefined8 *puVar1;
  long lVar2;
  undefined *puVar3;
  int iVar4;
  long lVar5;
  long lVar6;
  long lVar7;
  long *plVar8;
  ulong uVar9;
  undefined8 uVar10;
  undefined8 *puVar11;
  undefined8 uVar12;
  undefined8 *puVar13;
  int *piVar14;
  undefined8 *puStack_228;
  undefined8 uStack_220;
  undefined8 *puStack_218;
  undefined8 uStack_210;
  undefined8 *puStack_208;
  undefined8 uStack_200;
  undefined8 *puStack_1f8;
  undefined8 uStack_1f0;
  undefined8 *puStack_1e8;
  undefined8 uStack_1e0;
  undefined8 *puStack_1d8;
  undefined8 uStack_1d0;
  undefined8 *puStack_1c8;
  undefined8 uStack_1c0;
  undefined8 *puStack_1b8;
  undefined8 uStack_1b0;
  undefined8 *puStack_1a8;
  undefined8 uStack_1a0;
  undefined8 *puStack_198;
  undefined8 uStack_190;
  undefined8 *puStack_188;
  undefined8 uStack_180;
  undefined8 *puStack_178;
  undefined8 uStack_170;
  undefined8 *puStack_168;
  undefined8 uStack_160;
  undefined8 *puStack_158;
  undefined8 uStack_150;
  undefined8 *puStack_148;
  undefined8 uStack_140;
  undefined8 *puStack_138;
  undefined8 uStack_130;
  undefined8 *puStack_128;
  ulong uStack_120;
  long lStack_118;
  long *aplStack_110 [2];
  undefined8 *puStack_100;
  int iStack_f8;
  undefined2 uStack_f4;
  undefined2 uStack_f2;
  undefined4 uStack_f0;
  undefined2 uStack_ec;
  undefined2 uStack_ea;
  undefined2 uStack_e8;
  undefined2 uStack_e6;
  undefined2 uStack_e4;
  undefined2 uStack_e2;
  undefined2 uStack_e0;
  undefined2 uStack_de;
  undefined2 uStack_dc;
  undefined2 uStack_da;
  undefined2 uStack_d8;
  undefined2 uStack_d6;
  undefined2 uStack_d4;
  undefined2 uStack_d2;
  undefined2 uStack_d0;
  undefined2 uStack_ce;
  undefined4 uStack_cc;
  undefined2 uStack_c8;
  long lStack_c0;
  long *plStack_b0;
  long alStack_a0 [7];
  long lStack_68;
  
  lVar2 = tpidr_el0;
  lStack_68 = *(long *)(lVar2 + 0x28);
  FUN_0405ccb0();
  puStack_128 = (undefined8 *)0x0;
  uStack_120 = 0;
  if (((bRam000000000a4bc630 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc630), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_0020135e;
    uStack_f4 = (undefined2)((ulong)_UNK_0020135e >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_0020135e >> 0x30);
    puStack_100 = _UNK_00201356;
    uStack_e8 = (undefined2)_UNK_0020136e;
    uStack_e6 = (undefined2)((ulong)_UNK_0020136e >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_0020136e >> 0x20);
    uStack_f0 = (undefined4)_UNK_00201366;
    uStack_ec = (undefined2)((ulong)_UNK_00201366 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_00201366 >> 0x30);
    uStack_e2 = 0x67;
    uStack_e0 = 0x65;
    uStack_de = 0x74;
    uStack_dc = 0;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc628 = lStack_118;
    FUN_08d03480(0xa4bc630);
  }
  lVar5 = lRam000000000a4bc628;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x680);
  puStack_138 = (undefined8 *)0x0;
  uStack_130 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_138 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_130 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_138 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_138);
  if (puStack_138 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc640 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc640), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_0042858c;
    uStack_f4 = (undefined2)((ulong)_UNK_0042858c >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_0042858c >> 0x30);
    puStack_100 = _UNK_00428584;
    uStack_e8 = (undefined2)_UNK_0042859c;
    uStack_e6 = (undefined2)((ulong)_UNK_0042859c >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_0042859c >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_0042859c >> 0x30);
    uStack_f0 = (undefined4)_UNK_00428594;
    uStack_ec = (undefined2)((ulong)_UNK_00428594 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_00428594 >> 0x30);
    uStack_e0 = 0x69;
    uStack_de = 99;
    uStack_dc = 0x65;
    uStack_da = 0;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc638 = lStack_118;
    FUN_08d03480(0xa4bc640);
  }
  lVar5 = lRam000000000a4bc638;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x678);
  puStack_148 = (undefined8 *)0x0;
  uStack_140 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_148 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_140 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_148 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_148);
  if (puStack_148 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc650 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc650), iVar4 != 0)) {
    uStack_d8 = (undefined2)_UNK_002bd226;
    uStack_d6 = (undefined2)((ulong)_UNK_002bd226 >> 0x10);
    uStack_d4 = (undefined2)((ulong)_UNK_002bd226 >> 0x20);
    uStack_d2 = (undefined2)((ulong)_UNK_002bd226 >> 0x30);
    uStack_e0 = (undefined2)_UNK_002bd21e;
    uStack_de = (undefined2)((ulong)_UNK_002bd21e >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_002bd21e >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_002bd21e >> 0x30);
    iStack_f8 = (int)_UNK_002bd206;
    uStack_f4 = (undefined2)((ulong)_UNK_002bd206 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002bd206 >> 0x30);
    puStack_100 = _UNK_002bd1fe;
    uStack_e8 = (undefined2)_UNK_002bd216;
    uStack_e6 = (undefined2)((ulong)_UNK_002bd216 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002bd216 >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_002bd216 >> 0x30);
    uStack_f0 = (undefined4)_UNK_002bd20e;
    uStack_ec = (undefined2)((ulong)_UNK_002bd20e >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002bd20e >> 0x30);
    uStack_d0 = 0x70;
    uStack_ce = 0;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc648 = lStack_118;
    FUN_08d03480(0xa4bc650);
  }
  lVar5 = lRam000000000a4bc648;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x510);
  puStack_158 = (undefined8 *)0x0;
  uStack_150 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_158 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_150 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_158 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_158);
  if (puStack_158 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc660 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc660), iVar4 != 0)) {
    uStack_d8 = (undefined2)_UNK_002bd72a;
    uStack_d6 = (undefined2)((ulong)_UNK_002bd72a >> 0x10);
    uStack_d4 = (undefined2)((ulong)_UNK_002bd72a >> 0x20);
    uStack_d2 = (undefined2)((ulong)_UNK_002bd72a >> 0x30);
    uStack_e0 = (undefined2)_UNK_002bd722;
    uStack_de = (undefined2)((ulong)_UNK_002bd722 >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_002bd722 >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_002bd722 >> 0x30);
    iStack_f8 = (int)_UNK_002bd70a;
    uStack_f4 = (undefined2)((ulong)_UNK_002bd70a >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002bd70a >> 0x30);
    puStack_100 = _UNK_002bd702;
    uStack_e8 = (undefined2)_UNK_002bd71a;
    uStack_e6 = (undefined2)((ulong)_UNK_002bd71a >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002bd71a >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_002bd71a >> 0x30);
    uStack_f0 = (undefined4)_UNK_002bd712;
    uStack_ec = (undefined2)((ulong)_UNK_002bd712 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002bd712 >> 0x30);
    uStack_d0 = 0x70;
    uStack_ce = 0;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc658 = lStack_118;
    FUN_08d03480(0xa4bc660);
  }
  lVar5 = lRam000000000a4bc658;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x5f8);
  puStack_168 = (undefined8 *)0x0;
  uStack_160 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_168 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_160 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_168 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_168);
  if (puStack_168 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc670 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc670), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_001bfd90;
    uStack_f4 = (undefined2)((ulong)_UNK_001bfd90 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_001bfd90 >> 0x30);
    puStack_100 = _UNK_001bfd88;
    uStack_e8 = (undefined2)_UNK_001bfda0;
    uStack_e6 = (undefined2)((uint)_UNK_001bfda0 >> 0x10);
    uStack_f0 = (undefined4)_UNK_001bfd98;
    uStack_ec = (undefined2)((ulong)_UNK_001bfd98 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_001bfd98 >> 0x30);
    uStack_dc = (undefined2)_UNK_001bfdac;
    uStack_da = (undefined2)((ulong)_UNK_001bfdac >> 0x10);
    uStack_d8 = (undefined2)((ulong)_UNK_001bfdac >> 0x20);
    uStack_d6 = (undefined2)((ulong)_UNK_001bfdac >> 0x30);
    uStack_e4 = (undefined2)_UNK_001bfda4;
    uStack_e2 = (undefined2)((uint)_UNK_001bfda4 >> 0x10);
    uStack_e0 = (undefined2)_UNK_001bfda8;
    uStack_de = (undefined2)((uint)_UNK_001bfda8 >> 0x10);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc668 = lStack_118;
    FUN_08d03480(0xa4bc670);
  }
  lVar5 = lRam000000000a4bc668;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x518);
  puStack_178 = (undefined8 *)0x0;
  uStack_170 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_178 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_170 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_178 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_178);
  if (puStack_178 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc680 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc680), iVar4 != 0)) {
    uStack_d8 = (undefined2)_UNK_00364cf6;
    uStack_d6 = (undefined2)((ulong)_UNK_00364cf6 >> 0x10);
    uStack_d4 = (undefined2)((ulong)_UNK_00364cf6 >> 0x20);
    uStack_d2 = (undefined2)((ulong)_UNK_00364cf6 >> 0x30);
    uStack_e0 = (undefined2)_UNK_00364cee;
    uStack_de = (undefined2)((ulong)_UNK_00364cee >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_00364cee >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_00364cee >> 0x30);
    iStack_f8 = (int)_UNK_00364cd6;
    uStack_f4 = (undefined2)((ulong)_UNK_00364cd6 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_00364cd6 >> 0x30);
    puStack_100 = _UNK_00364cce;
    uStack_e8 = (undefined2)_UNK_00364ce6;
    uStack_e6 = (undefined2)((ulong)_UNK_00364ce6 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_00364ce6 >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_00364ce6 >> 0x30);
    uStack_f0 = (undefined4)_UNK_00364cde;
    uStack_ec = (undefined2)((ulong)_UNK_00364cde >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_00364cde >> 0x30);
    uStack_d0 = 0x69;
    uStack_ce = 0x6e;
    uStack_cc = 0x67;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc678 = lStack_118;
    FUN_08d03480(0xa4bc680);
  }
  lVar5 = lRam000000000a4bc678;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x568);
  puStack_188 = (undefined8 *)0x0;
  uStack_180 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_188 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_180 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_188 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_188);
  if (puStack_188 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc690 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc690), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_003652c2;
    uStack_f4 = (undefined2)((ulong)_UNK_003652c2 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_003652c2 >> 0x30);
    puStack_100 = _UNK_003652ba;
    uStack_e8 = (undefined2)_UNK_003652d2;
    uStack_e6 = (undefined2)((uint6)_UNK_003652d2 >> 0x10);
    uStack_e4 = (undefined2)((uint6)_UNK_003652d2 >> 0x20);
    uStack_f0 = (undefined4)_UNK_003652ca;
    uStack_ec = (undefined2)((ulong)_UNK_003652ca >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_003652ca >> 0x30);
    uStack_da = (undefined2)_UNK_003652e0;
    uStack_d8 = (undefined2)((ulong)_UNK_003652e0 >> 0x10);
    uStack_d6 = (undefined2)((ulong)_UNK_003652e0 >> 0x20);
    uStack_d4 = (undefined2)((ulong)_UNK_003652e0 >> 0x30);
    uStack_e2 = _UNK_003652d8;
    uStack_e0 = (undefined2)_UNK_003652da;
    uStack_de = (undefined2)((uint6)_UNK_003652da >> 0x10);
    uStack_dc = (undefined2)((uint6)_UNK_003652da >> 0x20);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc688 = lStack_118;
    FUN_08d03480(0xa4bc690);
  }
  lVar5 = lRam000000000a4bc688;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x558);
  puStack_198 = (undefined8 *)0x0;
  uStack_190 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_198 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_190 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_198 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_198);
  if (puStack_198 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc6a0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc6a0), iVar4 != 0)) {
    uStack_d8 = (undefined2)_UNK_00365146;
    uStack_d6 = (undefined2)((ulong)_UNK_00365146 >> 0x10);
    uStack_d4 = (undefined2)((ulong)_UNK_00365146 >> 0x20);
    uStack_d2 = (undefined2)((ulong)_UNK_00365146 >> 0x30);
    uStack_e0 = (undefined2)_UNK_0036513e;
    uStack_de = (undefined2)((ulong)_UNK_0036513e >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_0036513e >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_0036513e >> 0x30);
    iStack_f8 = (int)_UNK_00365126;
    uStack_f4 = (undefined2)((ulong)_UNK_00365126 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_00365126 >> 0x30);
    puStack_100 = _UNK_0036511e;
    uStack_e8 = (undefined2)_UNK_00365136;
    uStack_e6 = (undefined2)((ulong)_UNK_00365136 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_00365136 >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_00365136 >> 0x30);
    uStack_f0 = (undefined4)_UNK_0036512e;
    uStack_ec = (undefined2)((ulong)_UNK_0036512e >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_0036512e >> 0x30);
    uStack_d0 = 0x69;
    uStack_ce = 0x6e;
    uStack_cc = 0x67;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc698 = lStack_118;
    FUN_08d03480(0xa4bc6a0);
  }
  lVar5 = lRam000000000a4bc698;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x560);
  puStack_1a8 = (undefined8 *)0x0;
  uStack_1a0 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_1a8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_1a0 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_1a8 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_1a8);
  if (puStack_1a8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc6b0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc6b0), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_0036506e;
    uStack_f4 = (undefined2)((ulong)_UNK_0036506e >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_0036506e >> 0x30);
    puStack_100 = _UNK_00365066;
    uStack_e8 = (undefined2)_UNK_0036507e;
    uStack_e6 = (undefined2)((uint6)_UNK_0036507e >> 0x10);
    uStack_e4 = (undefined2)((uint6)_UNK_0036507e >> 0x20);
    uStack_f0 = (undefined4)_UNK_00365076;
    uStack_ec = (undefined2)((ulong)_UNK_00365076 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_00365076 >> 0x30);
    uStack_da = (undefined2)_UNK_0036508c;
    uStack_d8 = (undefined2)((ulong)_UNK_0036508c >> 0x10);
    uStack_d6 = (undefined2)((ulong)_UNK_0036508c >> 0x20);
    uStack_d4 = (undefined2)((ulong)_UNK_0036508c >> 0x30);
    uStack_e2 = _UNK_00365084;
    uStack_e0 = (undefined2)_UNK_00365086;
    uStack_de = (undefined2)((uint6)_UNK_00365086 >> 0x10);
    uStack_dc = (undefined2)((uint6)_UNK_00365086 >> 0x20);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc6a8 = lStack_118;
    FUN_08d03480(0xa4bc6b0);
  }
  lVar5 = lRam000000000a4bc6a8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x578);
  puStack_1b8 = (undefined8 *)0x0;
  uStack_1b0 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_1b8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_1b0 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_1b8 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_1b8);
  if (puStack_1b8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc6c0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc6c0), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_003653ae;
    uStack_f4 = (undefined2)((ulong)_UNK_003653ae >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_003653ae >> 0x30);
    puStack_100 = _UNK_003653a6;
    uStack_e8 = (undefined2)_UNK_003653be;
    uStack_e6 = (undefined2)((uint6)_UNK_003653be >> 0x10);
    uStack_e4 = (undefined2)((uint6)_UNK_003653be >> 0x20);
    uStack_f0 = (undefined4)_UNK_003653b6;
    uStack_ec = (undefined2)((ulong)_UNK_003653b6 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_003653b6 >> 0x30);
    uStack_da = (undefined2)_UNK_003653cc;
    uStack_d8 = (undefined2)((ulong)_UNK_003653cc >> 0x10);
    uStack_d6 = (undefined2)((ulong)_UNK_003653cc >> 0x20);
    uStack_d4 = (undefined2)((ulong)_UNK_003653cc >> 0x30);
    uStack_e2 = _UNK_003653c4;
    uStack_e0 = (undefined2)_UNK_003653c6;
    uStack_de = (undefined2)((uint6)_UNK_003653c6 >> 0x10);
    uStack_dc = (undefined2)((uint6)_UNK_003653c6 >> 0x20);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc6b8 = lStack_118;
    FUN_08d03480(0xa4bc6c0);
  }
  lVar5 = lRam000000000a4bc6b8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x580);
  puStack_1c8 = (undefined8 *)0x0;
  uStack_1c0 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_1c8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_1c0 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_1c8 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_1c8);
  if (puStack_1c8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc6d0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc6d0), iVar4 != 0)) {
    uStack_d8 = _UNK_002b3e1c;
    uStack_e0 = (undefined2)_UNK_002b3e14;
    uStack_de = (undefined2)((ulong)_UNK_002b3e14 >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_002b3e14 >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_002b3e14 >> 0x30);
    iStack_f8 = (int)_UNK_002b3dfc;
    uStack_f4 = (undefined2)((ulong)_UNK_002b3dfc >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002b3dfc >> 0x30);
    puStack_100 = _UNK_002b3df4;
    uStack_e8 = (undefined2)_UNK_002b3e0c;
    uStack_e6 = (undefined2)((ulong)_UNK_002b3e0c >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002b3e0c >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_002b3e0c >> 0x30);
    uStack_f0 = (undefined4)_UNK_002b3e04;
    uStack_ec = (undefined2)((ulong)_UNK_002b3e04 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002b3e04 >> 0x30);
    uStack_ce = (undefined2)_UNK_002b3e26;
    uStack_cc = (undefined4)((ulong)_UNK_002b3e26 >> 0x10);
    uStack_c8 = (undefined2)((ulong)_UNK_002b3e26 >> 0x30);
    uStack_d6 = (undefined2)_UNK_002b3e1e;
    uStack_d4 = (undefined2)((uint6)_UNK_002b3e1e >> 0x10);
    uStack_d2 = (undefined2)((uint6)_UNK_002b3e1e >> 0x20);
    uStack_d0 = _UNK_002b3e24;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc6c8 = lStack_118;
    FUN_08d03480(0xa4bc6d0);
  }
  lVar5 = lRam000000000a4bc6c8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x570);
  puStack_1d8 = (undefined8 *)0x0;
  uStack_1d0 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_1d8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_1d0 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_1d8 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_1d8);
  if (puStack_1d8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc6e0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc6e0), iVar4 != 0)) {
    uStack_d8 = (undefined2)_UNK_002b3de4;
    uStack_d6 = (undefined2)((ulong)_UNK_002b3de4 >> 0x10);
    uStack_d4 = (undefined2)((ulong)_UNK_002b3de4 >> 0x20);
    uStack_d2 = (undefined2)((ulong)_UNK_002b3de4 >> 0x30);
    uStack_e0 = (undefined2)_UNK_002b3ddc;
    uStack_de = (undefined2)((ulong)_UNK_002b3ddc >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_002b3ddc >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_002b3ddc >> 0x30);
    iStack_f8 = (int)_UNK_002b3dc4;
    uStack_f4 = (undefined2)((ulong)_UNK_002b3dc4 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002b3dc4 >> 0x30);
    puStack_100 = _UNK_002b3dbc;
    uStack_e8 = (undefined2)_UNK_002b3dd4;
    uStack_e6 = (undefined2)((ulong)_UNK_002b3dd4 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002b3dd4 >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_002b3dd4 >> 0x30);
    uStack_f0 = (undefined4)_UNK_002b3dcc;
    uStack_ec = (undefined2)((ulong)_UNK_002b3dcc >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002b3dcc >> 0x30);
    uStack_d0 = 100;
    uStack_ce = 0x65;
    uStack_cc = 0x72;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc6d8 = lStack_118;
    FUN_08d03480(0xa4bc6e0);
  }
  lVar5 = lRam000000000a4bc6d8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x590);
  puStack_1e8 = (undefined8 *)0x0;
  uStack_1e0 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_1e8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_1e0 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_1e8 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_1e8);
  if (puStack_1e8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc6f0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc6f0), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_002f5c8c;
    uStack_f4 = (undefined2)((uint6)_UNK_002f5c8c >> 0x20);
    puStack_100 = _UNK_002f5c84;
    uStack_ea = (undefined2)_UNK_002f5c9a;
    uStack_e8 = (undefined2)((ulong)_UNK_002f5c9a >> 0x10);
    uStack_e6 = (undefined2)((ulong)_UNK_002f5c9a >> 0x20);
    uStack_e4 = (undefined2)((ulong)_UNK_002f5c9a >> 0x30);
    uStack_f2 = _UNK_002f5c92;
    uStack_f0 = (undefined4)_UNK_002f5c94;
    uStack_ec = (undefined2)((uint6)_UNK_002f5c94 >> 0x20);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc6e8 = lStack_118;
    FUN_08d03480(0xa4bc6f0);
  }
  lVar5 = lRam000000000a4bc6e8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x6b0);
  puStack_1f8 = (undefined8 *)0x0;
  uStack_1f0 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_1f8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_1f0 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_1f8 = puStack_100;
  FUN_069cae94(uVar12,&puStack_1f8);
  if (puStack_1f8 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  if (((bRam000000000a4bc700 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc700), iVar4 != 0)) {
    iStack_f8 = _UNK_002f5caa;
    puStack_100 = _UNK_002f5ca2;
    uStack_ec = (undefined2)_UNK_002f5cb6;
    uStack_ea = (undefined2)((ulong)_UNK_002f5cb6 >> 0x10);
    uStack_e8 = (undefined2)((ulong)_UNK_002f5cb6 >> 0x20);
    uStack_e6 = (undefined2)((ulong)_UNK_002f5cb6 >> 0x30);
    uStack_f4 = (undefined2)_UNK_002f5cae;
    uStack_f2 = (undefined2)((uint)_UNK_002f5cae >> 0x10);
    uStack_f0 = _UNK_002f5cb2;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc6f8 = lStack_118;
    FUN_08d03480(0xa4bc700);
  }
  lVar5 = lRam000000000a4bc6f8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x6b8);
  puStack_208 = (undefined8 *)0x0;
  uStack_200 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_208 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_200 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_208 = puStack_100;
  FUN_069cae94(uVar12,&puStack_208);
  puVar13 = puStack_128;
  if (puStack_208 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x668);
  puStack_218 = (undefined8 *)0x0;
  uStack_210 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_218 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_210 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_218 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_218);
  if (puStack_218 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  lVar5 = *(long *)(param_1 + 0x6e0);
  if (((bRam000000000a4bc710 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc710), iVar4 != 0)) {
    uStack_e0 = 0;
    iStack_f8 = (int)_UNK_002ddfe4;
    uStack_f4 = (undefined2)((ulong)_UNK_002ddfe4 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002ddfe4 >> 0x30);
    puStack_100 = _UNK_002ddfdc;
    uStack_e8 = (undefined2)_UNK_002ddff4;
    uStack_e6 = (undefined2)((ulong)_UNK_002ddff4 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002ddff4 >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_002ddff4 >> 0x30);
    uStack_f0 = (undefined4)_UNK_002ddfec;
    uStack_ec = (undefined2)((ulong)_UNK_002ddfec >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002ddfec >> 0x30);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc708 = lStack_118;
    FUN_08d03480(0xa4bc710);
  }
  lVar6 = lRam000000000a4bc708;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  plVar8 = (long *)(lVar5 + 0x568);
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar6;
  uStack_f4 = (undefined2)((ulong)lVar6 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar6 >> 0x30);
  lVar7 = 0;
  if (lVar6 != 0) {
    lVar6 = FUN_022a3668(&puStack_100);
    lVar7 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
    if (lVar6 != 0) {
      FUN_022573b4(lVar6,lVar7);
      lVar7 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
    }
  }
  puVar13 = puStack_100;
  FUN_02241dac(plVar8);
  iVar4 = *(int *)(lVar5 + 0x570);
  *(uint *)(lVar5 + 0x570) = iVar4 + 1U;
  if (*(uint *)(lVar5 + 0x574) < iVar4 + 1U) {
    FUN_01ed7288(plVar8,iVar4);
  }
  plVar8 = (long *)(*plVar8 + (long)iVar4 * 0x10);
  *plVar8 = (long)puVar13;
  plVar8[1] = lVar7;
  lVar5 = *(long *)(param_1 + 0x4a8);
  if (lVar5 != 0) {
    FUN_01ec2f94(&puStack_100,&UNK_0065d83a);
    FUN_01f5c200(aplStack_110,&puStack_100);
    FUN_0701e870(lVar5,aplStack_110);
    if (aplStack_110[0] != (long *)0x0) {
      (**(code **)(*aplStack_110[0] + 0x18))();
    }
    if (puStack_100 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
    FUN_06c1000c(*(long *)(param_1 + 0x4a8) + 0x408,param_1,FUN_06c10204,0);
    FUN_06c102d8(*(long *)(param_1 + 0x4a8) + 0x3f0,param_1,FUN_06c104d0,0);
  }
  lVar5 = *(long *)(param_1 + 0x4b0);
  if (((bRam000000000a4ad680 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4ad680), iVar4 != 0)) {
    uStack_d0 = 0;
    uStack_d8 = (undefined2)_UNK_002e7b12;
    uStack_d6 = (undefined2)((ulong)_UNK_002e7b12 >> 0x10);
    uStack_d4 = (undefined2)((ulong)_UNK_002e7b12 >> 0x20);
    uStack_d2 = (undefined2)((ulong)_UNK_002e7b12 >> 0x30);
    uStack_e0 = (undefined2)_UNK_002e7b0a;
    uStack_de = (undefined2)((ulong)_UNK_002e7b0a >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_002e7b0a >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_002e7b0a >> 0x30);
    iStack_f8 = (int)_UNK_002e7af2;
    uStack_f4 = (undefined2)((ulong)_UNK_002e7af2 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002e7af2 >> 0x30);
    puStack_100 = _UNK_002e7aea;
    uStack_e8 = (undefined2)_UNK_002e7b02;
    uStack_e6 = (undefined2)((ulong)_UNK_002e7b02 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002e7b02 >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_002e7b02 >> 0x30);
    uStack_f0 = (undefined4)_UNK_002e7afa;
    uStack_ec = (undefined2)((ulong)_UNK_002e7afa >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002e7afa >> 0x30);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4ad678 = lStack_118;
    FUN_08d03480(0xa4ad680);
  }
  lVar7 = lRam000000000a4ad678;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar7;
  uStack_f4 = (undefined2)((ulong)lVar7 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar7 >> 0x30);
  if ((lVar7 != 0) && (lVar7 = FUN_022a3668(&puStack_100), lVar7 != 0)) {
    FUN_022573b4(lVar7,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(lVar5 + 0x568,&puStack_100);
  FUN_06c10a80(*(long *)(param_1 + 0x4a8) + 0x3d8,param_1,FUN_06c10c78,0);
  lVar5 = FUN_05f482cc(*(undefined8 *)(_DAT_0a4a4428 + 0x3860));
  lVar7 = FUN_05f8cb88(*(undefined8 *)(_DAT_0a4a4428 + 0x3860));
  if (*(int *)(lVar7 + 0x4b0) != 0) {
    lVar6 = (long)*(int *)(lVar7 + 0x4b0) << 4;
    piVar14 = (int *)(*(long *)(lVar7 + 0x4a8) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0x878);
        if (iVar4 == 0) goto code_r0x06c0d36c;
        goto LAB_06c0d31c;
      }
      lVar6 = lVar6 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar6 != 0);
  }
  lVar7 = FUN_05f8cb88(*(undefined8 *)(_DAT_0a4a4428 + 0x3860));
  FUN_06c10c80(lVar7 + 0x4a8,param_1,FUN_06c10e78,0);
  iVar4 = *(int *)(lVar5 + 0x878);
  if (iVar4 != 0) {
LAB_06c0d31c:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0x870) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0x890);
        if (iVar4 == 0) goto code_r0x06c0d3d8;
        goto LAB_06c0d388;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d36c:
  FUN_06c10a80(lVar5 + 0x870,param_1,FUN_06c10e80,0);
  iVar4 = *(int *)(lVar5 + 0x890);
  if (iVar4 != 0) {
LAB_06c0d388:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0x888) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0x8a8);
        if (iVar4 == 0) goto LAB_06c0d440;
        goto LAB_06c0d3f4;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d3d8:
  FUN_06c10e90(lVar5 + 0x888,param_1,FUN_06c11088,0);
  iVar4 = *(int *)(lVar5 + 0x8a8);
  if (iVar4 != 0) {
LAB_06c0d3f4:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0x8a0) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0x8c0);
        if (iVar4 == 0) goto code_r0x06c0d4b0;
        goto LAB_06c0d460;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
LAB_06c0d440:
  FUN_06c10a80(lVar5 + 0x8a0,param_1,Java_com_epicgames_unreal_NativeCalls_ForwardNotification,0);
  iVar4 = *(int *)(lVar5 + 0x8c0);
  if (iVar4 != 0) {
LAB_06c0d460:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0x8b8) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0x8d8);
        if (iVar4 == 0) goto code_r0x06c0d51c;
        goto LAB_06c0d4cc;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d4b0:
  FUN_06c10a80(lVar5 + 0x8b8,param_1,FUN_06c11edc,0);
  iVar4 = *(int *)(lVar5 + 0x8d8);
  if (iVar4 != 0) {
LAB_06c0d4cc:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0x8d0) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0x8f0);
        if (iVar4 == 0) goto code_r0x06c0d588;
        goto LAB_06c0d538;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d51c:
  FUN_06c11f40(lVar5 + 0x8d0,param_1,FUN_06c12138,0);
  iVar4 = *(int *)(lVar5 + 0x8f0);
  if (iVar4 != 0) {
LAB_06c0d538:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0x8e8) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0x168);
        if (iVar4 == 0) goto code_r0x06c0d5f4;
        goto LAB_06c0d5a4;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d588:
  FUN_06c132f4(lVar5 + 0x8e8,param_1,FUN_06c134ec,0);
  iVar4 = *(int *)(lVar5 + 0x168);
  if (iVar4 != 0) {
LAB_06c0d5a4:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0x160) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0xe80);
        if (iVar4 == 0) goto code_r0x06c0d660;
        goto LAB_06c0d610;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d5f4:
  FUN_06c10a80(lVar5 + 0x160,param_1,FUN_06c13b44,0);
  iVar4 = *(int *)(lVar5 + 0xe80);
  if (iVar4 != 0) {
LAB_06c0d610:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0xe78) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0x920);
        if (iVar4 == 0) goto code_r0x06c0d6cc;
        goto LAB_06c0d67c;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d660:
  FUN_06c132f4(lVar5 + 0xe78,param_1,FUN_06c13b50,0);
  iVar4 = *(int *)(lVar5 + 0x920);
  if (iVar4 != 0) {
LAB_06c0d67c:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0x918) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0)) {
        iVar4 = *(int *)(lVar5 + 0xe68);
        if (iVar4 == 0) goto code_r0x06c0d730;
        goto LAB_06c0d6e8;
      }
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d6cc:
  FUN_06c11f40(lVar5 + 0x918,param_1,FUN_06c13b60,0);
  iVar4 = *(int *)(lVar5 + 0xe68);
  if (iVar4 != 0) {
LAB_06c0d6e8:
    lVar7 = (long)iVar4 << 4;
    piVar14 = (int *)(*(long *)(lVar5 + 0xe60) + 8);
    do {
      if (((*piVar14 != 0) && (plVar8 = *(long **)(piVar14 + -2), plVar8 != (long *)0x0)) &&
         (uVar9 = (**(code **)(*plVar8 + 0x28))(plVar8,param_1), (uVar9 & 1) != 0))
      goto LAB_06c0d744;
      lVar7 = lVar7 + -0x10;
      piVar14 = piVar14 + 4;
    } while (lVar7 != 0);
  }
code_r0x06c0d730:
  FUN_06c10a80(lVar5 + 0xe60,param_1,FUN_06c13b78,0);
LAB_06c0d744:
  uVar12 = *(undefined8 *)(param_1 + 0x5b0);
  FUN_03fc7818(&puStack_100,*(undefined8 *)(param_1 + 0x5a8));
  FUN_0691fa1c(uVar12,&puStack_100);
  if (puStack_100 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  lVar5 = *(long *)(param_1 + 0x5b0);
  if (((bRam000000000a4bc720 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc720), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_001950e6;
    uStack_f4 = (undefined2)((ulong)_UNK_001950e6 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_001950e6 >> 0x30);
    puStack_100 = _UNK_001950de;
    uStack_e8 = (undefined2)_UNK_001950f6;
    uStack_e6 = (undefined2)((ulong)_UNK_001950f6 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_001950f6 >> 0x20);
    uStack_f0 = (undefined4)_UNK_001950ee;
    uStack_ec = (undefined2)((ulong)_UNK_001950ee >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_001950ee >> 0x30);
    uStack_e2 = 0x42;
    uStack_e0 = 0x6f;
    uStack_de = 0x78;
    uStack_dc = 0;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc718 = lStack_118;
    FUN_08d03480(0xa4bc720);
  }
  lVar7 = lRam000000000a4bc718;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar7;
  uStack_f4 = (undefined2)((ulong)lVar7 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar7 >> 0x30);
  if ((lVar7 != 0) && (lVar7 = FUN_022a3668(&puStack_100), lVar7 != 0)) {
    FUN_022573b4(lVar7,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(lVar5 + 0x3d8,&puStack_100);
  lVar5 = *(long *)(param_1 + 0x5b0);
  if (((bRam000000000a4bc730 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc730), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_0019510c;
    uStack_f4 = (undefined2)((ulong)_UNK_0019510c >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_0019510c >> 0x30);
    puStack_100 = _UNK_00195104;
    uStack_e8 = _UNK_0019511c;
    uStack_f0 = (undefined4)_UNK_00195114;
    uStack_ec = (undefined2)((ulong)_UNK_00195114 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_00195114 >> 0x30);
    uStack_de = (undefined2)_UNK_00195126;
    uStack_dc = (undefined2)((ulong)_UNK_00195126 >> 0x10);
    uStack_da = (undefined2)((ulong)_UNK_00195126 >> 0x20);
    uStack_d8 = (undefined2)((ulong)_UNK_00195126 >> 0x30);
    uStack_e6 = (undefined2)_UNK_0019511e;
    uStack_e4 = (undefined2)((uint6)_UNK_0019511e >> 0x10);
    uStack_e2 = (undefined2)((uint6)_UNK_0019511e >> 0x20);
    uStack_e0 = _UNK_00195124;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc728 = lStack_118;
    FUN_08d03480(0xa4bc730);
  }
  lVar7 = lRam000000000a4bc728;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar7;
  uStack_f4 = (undefined2)((ulong)lVar7 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar7 >> 0x30);
  if ((lVar7 != 0) && (lVar7 = FUN_022a3668(&puStack_100), lVar7 != 0)) {
    FUN_022573b4(lVar7,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(lVar5 + 1000,&puStack_100);
  if (((bRam000000000a4bc740 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4bc740), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_002ee67c;
    uStack_f4 = (undefined2)((ulong)_UNK_002ee67c >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002ee67c >> 0x30);
    puStack_100 = _UNK_002ee674;
    uStack_e8 = (undefined2)_UNK_002ee68c;
    uStack_e6 = (undefined2)((ulong)_UNK_002ee68c >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002ee68c >> 0x20);
    uStack_f0 = (undefined4)_UNK_002ee684;
    uStack_ec = (undefined2)((ulong)_UNK_002ee684 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002ee684 >> 0x30);
    uStack_e2 = 0x69;
    uStack_e0 = 0x6f;
    uStack_de = 0x6e;
    uStack_dc = 0;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4bc738 = lStack_118;
    FUN_08d03480(0xa4bc740);
  }
  lVar5 = lRam000000000a4bc738;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar5;
  uStack_f4 = (undefined2)((ulong)lVar5 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar5 >> 0x30);
  if ((lVar5 != 0) && (lVar5 = FUN_022a3668(&puStack_100), lVar5 != 0)) {
    FUN_022573b4(lVar5,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(&puStack_128,&puStack_100);
  puVar13 = puStack_128;
  iVar4 = (int)uStack_120;
  uVar12 = *(undefined8 *)(param_1 + 0x5c8);
  puStack_228 = (undefined8 *)0x0;
  uStack_220 = 0;
  puStack_100 = (undefined8 *)0x0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  iStack_f8 = (int)uStack_120;
  if ((int)uStack_120 != 0) {
    FUN_020d9860(&puStack_100,uStack_120 & 0xffffffff,0);
    puVar11 = puStack_100;
    do {
      *puVar11 = 0;
      puVar11[1] = 0;
      iVar4 = iVar4 + -1;
      *puVar11 = *puVar13;
      puVar1 = puVar13 + 1;
      puVar13 = puVar13 + 2;
      puVar11[1] = *puVar1;
      puVar11 = puVar11 + 2;
    } while (iVar4 != 0);
    if (puStack_228 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
      FUN_01f18da4();
    }
  }
  uStack_220 = CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8));
  puStack_228 = puStack_100;
  FUN_069cb2a4(uVar12,&puStack_228);
  if (puStack_228 != (undefined8 *)0x0) {
                    /* WARNING: Subroutine does not return */
    FUN_01f18da4();
  }
  FUN_02270220(&puStack_128,param_1);
  puVar3 = PTR_DAT_0a11eb70;
  FUN_0682e3dc(*(undefined8 *)PTR_DAT_0a11eb70,*(undefined8 *)(param_1 + 0x518),0x4f,1);
  FUN_0682e3dc(*(undefined8 *)puVar3,*(undefined8 *)(param_1 + 0x518),0x50,1);
  lVar5 = *(long *)(param_1 + 0x710);
  if (((bRam000000000a4ad6c0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4ad6c0), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_002e8d0e;
    uStack_f4 = (undefined2)((ulong)_UNK_002e8d0e >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002e8d0e >> 0x30);
    puStack_100 = _UNK_002e8d06;
    uStack_e8 = _UNK_002e8d1e;
    uStack_f0 = (undefined4)_UNK_002e8d16;
    uStack_ec = (undefined2)((ulong)_UNK_002e8d16 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002e8d16 >> 0x30);
    uStack_de = (undefined2)_UNK_002e8d28;
    uStack_dc = (undefined2)((ulong)_UNK_002e8d28 >> 0x10);
    uStack_da = (undefined2)((ulong)_UNK_002e8d28 >> 0x20);
    uStack_d8 = (undefined2)((ulong)_UNK_002e8d28 >> 0x30);
    uStack_e6 = (undefined2)_UNK_002e8d20;
    uStack_e4 = (undefined2)((uint6)_UNK_002e8d20 >> 0x10);
    uStack_e2 = (undefined2)((uint6)_UNK_002e8d20 >> 0x20);
    uStack_e0 = _UNK_002e8d26;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4ad6b8 = lStack_118;
    FUN_08d03480(0xa4ad6c0);
  }
  lVar7 = lRam000000000a4ad6b8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar7;
  uStack_f4 = (undefined2)((ulong)lVar7 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar7 >> 0x30);
  if ((lVar7 != 0) && (lVar7 = FUN_022a3668(&puStack_100), lVar7 != 0)) {
    FUN_022573b4(lVar7,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(lVar5 + 3000,&puStack_100);
  lVar5 = *(long *)(param_1 + 0x718);
  if (((bRam000000000a4ad6e0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4ad6e0), iVar4 != 0)) {
    uStack_d8 = (undefined2)_UNK_002e8f8e;
    uStack_d6 = (undefined2)((ulong)_UNK_002e8f8e >> 0x10);
    uStack_d4 = (undefined2)((ulong)_UNK_002e8f8e >> 0x20);
    uStack_d2 = (undefined2)((ulong)_UNK_002e8f8e >> 0x30);
    uStack_e0 = (undefined2)_UNK_002e8f86;
    uStack_de = (undefined2)((ulong)_UNK_002e8f86 >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_002e8f86 >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_002e8f86 >> 0x30);
    iStack_f8 = (int)_UNK_002e8f6e;
    uStack_f4 = (undefined2)((ulong)_UNK_002e8f6e >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002e8f6e >> 0x30);
    puStack_100 = _UNK_002e8f66;
    uStack_e8 = (undefined2)_UNK_002e8f7e;
    uStack_e6 = (undefined2)((ulong)_UNK_002e8f7e >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002e8f7e >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_002e8f7e >> 0x30);
    uStack_f0 = (undefined4)_UNK_002e8f76;
    uStack_ec = (undefined2)((ulong)_UNK_002e8f76 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002e8f76 >> 0x30);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4ad6d8 = lStack_118;
    FUN_08d03480(0xa4ad6e0);
  }
  lVar7 = lRam000000000a4ad6d8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar7;
  uStack_f4 = (undefined2)((ulong)lVar7 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar7 >> 0x30);
  if ((lVar7 != 0) && (lVar7 = FUN_022a3668(&puStack_100), lVar7 != 0)) {
    FUN_022573b4(lVar7,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(lVar5 + 3000,&puStack_100);
  lVar5 = *(long *)(param_1 + 0x720);
  if (((bRam000000000a4ad6f0 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4ad6f0), iVar4 != 0)) {
    uStack_d8 = (undefined2)_UNK_002e9a20;
    uStack_d6 = (undefined2)((ulong)_UNK_002e9a20 >> 0x10);
    uStack_d4 = (undefined2)((ulong)_UNK_002e9a20 >> 0x20);
    uStack_d2 = (undefined2)((ulong)_UNK_002e9a20 >> 0x30);
    uStack_e0 = (undefined2)_UNK_002e9a18;
    uStack_de = (undefined2)((ulong)_UNK_002e9a18 >> 0x10);
    uStack_dc = (undefined2)((ulong)_UNK_002e9a18 >> 0x20);
    uStack_da = (undefined2)((ulong)_UNK_002e9a18 >> 0x30);
    iStack_f8 = (int)_UNK_002e9a00;
    uStack_f4 = (undefined2)((ulong)_UNK_002e9a00 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_002e9a00 >> 0x30);
    puStack_100 = _UNK_002e99f8;
    uStack_e8 = (undefined2)_UNK_002e9a10;
    uStack_e6 = (undefined2)((ulong)_UNK_002e9a10 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_002e9a10 >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_002e9a10 >> 0x30);
    uStack_f0 = (undefined4)_UNK_002e9a08;
    uStack_ec = (undefined2)((ulong)_UNK_002e9a08 >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_002e9a08 >> 0x30);
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4ad6e8 = lStack_118;
    FUN_08d03480(0xa4ad6f0);
  }
  lVar7 = lRam000000000a4ad6e8;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar7;
  uStack_f4 = (undefined2)((ulong)lVar7 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar7 >> 0x30);
  if ((lVar7 != 0) && (lVar7 = FUN_022a3668(&puStack_100), lVar7 != 0)) {
    FUN_022573b4(lVar7,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(lVar5 + 3000,&puStack_100);
  lVar5 = *(long *)(param_1 + 0x730);
  iVar4 = *(int *)(lVar5 + 0x400);
  plVar8 = (long *)(lVar5 + 0x3f8);
  if (iVar4 == 0) {
LAB_06c0da6c:
    FUN_01ec217c(plVar8,0,3,0x10);
    *(undefined4 *)(lVar5 + 0x400) = 3;
  }
  else {
    if ((undefined8 *)*plVar8 != (undefined8 *)0x0) {
      (*(code *)**(undefined8 **)*plVar8)();
      iVar4 = *(int *)(lVar5 + 0x400);
    }
    if (iVar4 != 3) goto LAB_06c0da6c;
  }
  puVar13 = (undefined8 *)*plVar8;
  *puVar13 = &UNK_09c408c0;
  uVar12 = FUN_01ed891c();
  puVar13[2] = uVar12;
  *puVar13 = &UNK_09c4f828;
  *(undefined4 *)((long)puVar13 + 0x1c) = 0;
  *(undefined4 *)(puVar13 + 3) = 0;
  FUN_022a3430(puVar13 + 3,param_1);
  puVar13[4] = FUN_06c147f4;
  puVar13[5] = 0;
  lVar5 = *(long *)(param_1 + 0x728);
  iVar4 = *(int *)(lVar5 + 0x3e0);
  plVar8 = (long *)(lVar5 + 0x3d8);
  if (iVar4 == 0) {
LAB_06c0dafc:
    FUN_01ec217c(plVar8,0,3,0x10);
    *(undefined4 *)(lVar5 + 0x3e0) = 3;
  }
  else {
    if ((undefined8 *)*plVar8 != (undefined8 *)0x0) {
      (*(code *)**(undefined8 **)*plVar8)();
      iVar4 = *(int *)(lVar5 + 0x3e0);
    }
    if (iVar4 != 3) goto LAB_06c0dafc;
  }
  puVar13 = (undefined8 *)*plVar8;
  *puVar13 = &UNK_08d7d540;
  uVar12 = FUN_01ed891c();
  puVar13[2] = uVar12;
  *puVar13 = &UNK_09c4f4a8;
  *(undefined4 *)((long)puVar13 + 0x1c) = 0;
  *(undefined4 *)(puVar13 + 3) = 0;
  FUN_022a3430(puVar13 + 3,param_1);
  puVar13[4] = FUN_06c14968;
  puVar13[5] = 0;
  lVar5 = *(long *)(param_1 + 0x738);
  iVar4 = *(int *)(lVar5 + 0x3f0);
  plVar8 = (long *)(lVar5 + 1000);
  if (iVar4 != 0) {
    if ((undefined8 *)*plVar8 != (undefined8 *)0x0) {
      (*(code *)**(undefined8 **)*plVar8)();
      iVar4 = *(int *)(lVar5 + 0x3f0);
    }
    if (iVar4 == 3) goto LAB_06c0dba8;
  }
  FUN_01ec217c(plVar8,0,3,0x10);
  *(undefined4 *)(lVar5 + 0x3f0) = 3;
LAB_06c0dba8:
  puVar13 = (undefined8 *)*plVar8;
  *puVar13 = &UNK_09c42060;
  uVar12 = FUN_01ed891c();
  puVar13[2] = uVar12;
  *puVar13 = &UNK_09c4f8a8;
  *(undefined4 *)((long)puVar13 + 0x1c) = 0;
  *(undefined4 *)(puVar13 + 3) = 0;
  FUN_022a3430(puVar13 + 3,param_1);
  puVar13[4] = FUN_06c14a04;
  puVar13[5] = 0;
  lVar5 = *(long *)(param_1 + 0x6f8);
  if (((bRam000000000a4ad720 & 1) == 0) && (iVar4 = FUN_08d0333c(0xa4ad720), iVar4 != 0)) {
    iStack_f8 = (int)_UNK_001b1ee4;
    uStack_f4 = (undefined2)((ulong)_UNK_001b1ee4 >> 0x20);
    uStack_f2 = (undefined2)((ulong)_UNK_001b1ee4 >> 0x30);
    puStack_100 = _UNK_001b1edc;
    uStack_e8 = (undefined2)_UNK_001b1ef4;
    uStack_e6 = (undefined2)((ulong)_UNK_001b1ef4 >> 0x10);
    uStack_e4 = (undefined2)((ulong)_UNK_001b1ef4 >> 0x20);
    uStack_e2 = (undefined2)((ulong)_UNK_001b1ef4 >> 0x30);
    uStack_f0 = (undefined4)_UNK_001b1eec;
    uStack_ec = (undefined2)((ulong)_UNK_001b1eec >> 0x20);
    uStack_ea = (undefined2)((ulong)_UNK_001b1eec >> 0x30);
    uStack_e0 = 0x6f;
    uStack_de = 0x75;
    uStack_dc = 0x74;
    uStack_da = 0;
    FUN_0206e308(&lStack_118,&puStack_100,1);
    lRam000000000a4ad718 = lStack_118;
    FUN_08d03480(0xa4ad720);
  }
  lVar7 = lRam000000000a4ad718;
  puStack_100 = (undefined8 *)0x0;
  iStack_f8 = 0;
  uStack_f4 = 0;
  uStack_f2 = 0;
  FUN_022a3430(&puStack_100,param_1);
  iStack_f8 = (int)lVar7;
  uStack_f4 = (undefined2)((ulong)lVar7 >> 0x20);
  uStack_f2 = (undefined2)((ulong)lVar7 >> 0x30);
  if ((lVar7 != 0) && (lVar7 = FUN_022a3668(&puStack_100), lVar7 != 0)) {
    FUN_022573b4(lVar7,CONCAT26(uStack_f2,CONCAT24(uStack_f4,iStack_f8)));
  }
  FUN_0221900c(lVar5 + 0xbd8,&puStack_100);
  uVar12 = FUN_021cfc14();
  FUN_022842d8(uVar12,&UNK_005c4c8a);
  uVar10 = FUN_05cc4808();
  FUN_02284294(&puStack_100,uVar10);
  iStack_f8 = (int)uVar12;
  uStack_f4 = (undefined2)((ulong)uVar12 >> 0x20);
  uStack_f2 = (undefined2)((ulong)uVar12 >> 0x30);
  lVar5 = FUN_022821a0(&puStack_100);
  if (lStack_c0 != 0) {
    plVar8 = alStack_a0;
    if (plStack_b0 != (long *)0x0) {
      plVar8 = plStack_b0;
    }
    (**(code **)(*plVar8 + 0x10))();
  }
  if ((lVar5 != 0) && (DAT_0a1ff944 != '\0')) {
    thunk_FUN_02173234(lVar5);
  }
  *(long *)(param_1 + 0x7d8) = lVar5;
  if (puStack_128 == (undefined8 *)0x0) {
    if (*(long *)(lVar2 + 0x28) != lStack_68) {
                    /* WARNING: Subroutine does not return */
      __stack_chk_fail();
    }
    return;
  }
                    /* WARNING: Subroutine does not return */
  FUN_01f18da4();
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

- Decompiled functions: 20
- Candidate functions: 20
- Cancelled: false
