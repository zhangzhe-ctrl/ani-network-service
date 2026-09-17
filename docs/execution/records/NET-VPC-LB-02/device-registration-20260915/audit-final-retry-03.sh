#!/usr/bin/env bash
# Complete only the remaining tests of the same immutable candidate after resource interruptions.
set -Eeuo pipefail
source /home/ubuntu/.local/share/ani-network-service/env.sh
cd /home/ubuntu/workspace/ani-network-service-runs/snat-20260915T025202Z-d88ee066/source
test ! -e ../audit-final-retry-03.exit
test ! -e ../audit-final-retry-03.log
test ! -e ../artifacts
mkdir -m 700 ../audit-final-tmp-03
export TMPDIR="$(realpath ../audit-final-tmp-03)"
python3 - <<'CHECK'
import hashlib, json, pathlib
metadata = json.loads(pathlib.Path('../snapshot.json').read_text())
assert metadata['archive_sha256'] == '17d30aa89b7f9d100120166c4c6c218038c01f7fd8b8627a7c874a658980dbad'
for item in metadata['files']:
    path = pathlib.Path(item['path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], item['path']
    assert ('100755' if path.stat().st_mode & 0o111 else '100644') == item['mode'], item['path']
print('same immutable source verified:', len(metadata['files']))
CHECK
set +e
flock -n /home/ubuntu/.local/share/ani-network-service/net05a-heavy.lock \
  systemd-run --user --scope --quiet \
  -p CPUQuota=200% -p MemoryMax=2300M -p MemorySwapMax=0 \
  env TMPDIR="$TMPDIR" GOMAXPROCS=2 GOFLAGS=-p=2 GOMEMLIMIT=1500MiB \
  scripts/net05a-resource-guard bash -e -c '
    go test -race -list "^Test" ./internal/data > ../audit-data-test-list.txt
    scripts/integration -race ./internal/data -run "^(TestActualAdapterBlocksWrongOwnerChangedUIDAndUnexpectedChildren|TestConfirmedProviderRejectionFailsCreationButKeepsDeletionRecoverable|TestIntranetKCPlatformActualAdapterObservationAndRecovery|TestIntranetPlatformScopesDefaultsAllocationAndIndependentCapabilities|TestLBAdmissionAtomicIdentityReplayAndParentOccupancy|TestLBAdmissionCompetesWithSNATForOneClaimBothOrders|TestLBAdmissionRejectsCIDROnlyBackendAndDuplicateVIP|TestLBSchemaFrom0006PreservesAllOldColumnsAndDormantReservations|TestLBServiceProcessesRecoverUnknownMutationsWithTwoWorkers|TestLBUpdateRetainsRemovedSubnetUntilRouteAndBackendCleanup|TestNET05AAttachmentNotificationDuringClaimPreservesLeaseAndWake|TestNET05ACapacity|TestNET05AFairDueClaimsAcrossKindsTenantsAndParents|TestNET05AMigrationUpgradesAllThreeHistoricalChecksums|TestNET05ANotificationsDuringLeasePreservePendingAndPublicVersion|TestNET05AOldCacheAfterNewClaimCannotRegressOrCompleteNotification|TestNET05AStormCannotBypassBackoffOrCrossTenant|TestNET05OldestSubnetWorkIsNotStarvedByDueVPCObservation|TestNetworkWorkerOwnsVPCCreationAndConfirmedDeletion|TestPostgresRejectsPartialAcceptanceAndCrossTenantReferences|TestProviderOutageAndStaleGenerationCannotBecomeAvailable|TestRuntimeRoleCannotOwnOrElevateIntoSchemaOwner|TestServiceProcessesRecoverT1AndProviderSuccessWithoutCaller|TestSubnetAddressRaceAndParentDeletionRace|TestSubnetConcurrentPermanentIdempotencyAndDeletion|TestSubnetKCContractAndResidualReferencesBlockCleanup|TestSubnetMigrationUpgradesNET01WithoutChangingDurableFacts|TestSubnetProcessesRecoverT1ProviderSuccessAndUnknownDeletion|TestSubnetStaleParentRejectsNewIntentButNotPersistentReplay|TestSubnetTargetConstraintsAndPagination|TestSubnetUnknownCreateRetainsCIDRAndRejectsOldLeaseWrites|TestVPCAcceptanceIsTenantScopedAndReplaysExactly|TestVPCPagesRemainScopedAndCursorCannotChangeFilters)$" -timeout 12m -json
    mkdir ../artifacts
    go build -trimpath -o ../artifacts/lb-api ./scripts/lb-api
    go build -trimpath -o ../artifacts/network ./cmd/ani-network-service
    sha256sum ../artifacts/lb-api ../artifacts/network
  ' 2>&1 | tee ../audit-final-retry-03.log
result=$?
set -e
printf '%s\n' "$result" > ../audit-final-retry-03.exit
exit "$result"
