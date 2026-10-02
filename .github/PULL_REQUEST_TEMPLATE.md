<!-- 合并本 PR 前逐项自查；合并后分支清理是硬性动作，不靠记性 -->

## 合并后分支清理（硬性）
- [ ] 合并后**立即删除本分支**（GitHub 页面 Delete branch + 本地 `git branch -d <name>`）
      —— 仓库开分支从来不开 main，历史已因"开分支→PR 合→忘删"堆积过死分支

## 变更说明
<!-- 改了什么、为什么；关联的 plan/issue/交接文档小节 -->

## 领域包契约改动（涉及才勾）
- [ ] `domains/lubricant/contracts/state-machine.json` 变更已同步全部消费方：
      route_step / validate_state_machine / fixtures / 桌面端 lubricantContracts.ts（一致性测试会红）
- [ ] §5.2 回归门槛全绿（validate_schemas / validate_state_machine / e2e 系列）

## 自查
- [ ] 测试通过（前端 vitest / 领域包 §5.2 / workspace_bundle）
- [ ] Core 零侵入未破坏（业务逻辑只在 domains/lubricant/）
- [ ] 无合成数据进入 CLOSED（evidence_scope 语义未污染）
