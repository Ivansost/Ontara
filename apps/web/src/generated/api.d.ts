export interface paths {
    "/healthz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Healthz */
        get: operations["healthz_healthz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/readyz": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readyz */
        get: operations["readyz_readyz_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Session */
        get: operations["session_v1_session_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/catalogue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Catalogue */
        get: operations["catalogue_v1_catalogue_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/questions/{issue_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Questions */
        get: operations["questions_v1_questions__issue_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/locations/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Locations */
        post: operations["locations_v1_locations_resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/routes/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Route Preview */
        post: operations["route_preview_v1_routes_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Case */
        post: operations["create_case_v1_cases_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/cases/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Case */
        get: operations["read_case_v1_cases__case_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Edit Case */
        patch: operations["edit_case_v1_cases__case_id__patch"];
        trace?: never;
    };
    "/v1/cases/{case_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve */
        post: operations["approve_v1_cases__case_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/cases/{case_id}/follow-up": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Follow Up */
        post: operations["follow_up_v1_cases__case_id__follow_up_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/cases/{case_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_v1_cases__case_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/cases/{case_id}/timeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Timeline */
        get: operations["timeline_v1_cases__case_id__timeline_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/cases/{case_id}/evidence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Resident Evidence */
        get: operations["resident_evidence_v1_cases__case_id__evidence_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/cases/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Internal Case */
        get: operations["internal_case_internal_v1_cases__case_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/cases/{case_id}/versions/{version}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Internal Version */
        get: operations["internal_version_internal_v1_cases__case_id__versions__version__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/operations/{operation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Internal Operation */
        get: operations["internal_operation_internal_v1_operations__operation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/jobs/lease": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Lease */
        post: operations["lease_internal_v1_jobs_lease_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/jobs/{job_id}/heartbeat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Heartbeat */
        post: operations["heartbeat_internal_v1_jobs__job_id__heartbeat_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/jobs/{job_id}/abandon": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Abandon */
        post: operations["abandon_internal_v1_jobs__job_id__abandon_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/jobs/{job_id}/inspection-result": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Inspection Result */
        post: operations["inspection_result_internal_v1_jobs__job_id__inspection_result_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/operations/{operation_id}/transition": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Transition */
        post: operations["transition_internal_v1_operations__operation_id__transition_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/operations/{operation_id}/receipt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Receipt */
        post: operations["receipt_internal_v1_operations__operation_id__receipt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/operations/{operation_id}/fault": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Fault */
        post: operations["fault_internal_v1_operations__operation_id__fault_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/cases/{case_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Event */
        post: operations["event_internal_v1_cases__case_id__events_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/cases/{case_id}/evidence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Evidence */
        get: operations["evidence_internal_v1_cases__case_id__evidence_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/cases/{case_id}/follow-up-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Follow Up Request */
        post: operations["follow_up_request_internal_v1_cases__case_id__follow_up_request_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/cases/{case_id}/follow-up-inspection": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Follow Up Inspection */
        post: operations["follow_up_inspection_internal_v1_cases__case_id__follow_up_inspection_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/research/import": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Import Research */
        post: operations["import_research_internal_v1_research_import_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/research/imports/{batch_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Import Status */
        get: operations["import_status_internal_v1_research_imports__batch_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload Artifact */
        post: operations["upload_artifact_internal_v1_artifacts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/artifacts/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Artifact Metadata */
        get: operations["artifact_metadata_internal_v1_artifacts__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/artifacts/{artifact_id}/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Artifact Content */
        get: operations["artifact_content_internal_v1_artifacts__artifact_id__content_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/retrieval/procedures": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retrieve Procedures */
        post: operations["retrieve_procedures_internal_v1_retrieval_procedures_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/retrieval/lessons": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retrieve Lessons */
        post: operations["retrieve_lessons_internal_v1_retrieval_lessons_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/retrieval/lessons/promote": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Promote Lesson */
        post: operations["promote_lesson_internal_v1_retrieval_lessons_promote_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/retrieval/verify-record": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Verify Record */
        post: operations["verify_record_internal_v1_retrieval_verify_record_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/mail/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Mail Status */
        get: operations["mail_status_internal_v1_mail_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/mail/poll": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mail Poll */
        post: operations["mail_poll_internal_v1_mail_poll_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** AbandonRequest */
        AbandonRequest: {
            /** Workerid */
            workerId: string;
            /** Leasetoken */
            leaseToken: string;
            /**
             * Reason
             * @default process_exit
             */
            reason: string;
            /** Exitcode */
            exitCode?: number | null;
            /** Processid */
            processId?: number | null;
            /** Attemptid */
            attemptId?: string | null;
        };
        /** ApprovalRequest */
        ApprovalRequest: {
            /** Version */
            version: number;
        };
        /** ArtifactUpload */
        ArtifactUpload: {
            /** Id */
            id: string;
            /** Filename */
            filename: string;
            /** Mimetype */
            mimeType: string;
            /** Contentbase64 */
            contentBase64: string;
            /**
             * Visibility
             * @enum {string}
             */
            visibility: "public" | "case";
            /** Caseid */
            caseId?: string | null;
            /** Sourceid */
            sourceId?: string | null;
            /** Sourceversion */
            sourceVersion: string;
            /** Authorityid */
            authorityId?: string | null;
            /** Operationid */
            operationId?: string | null;
            /** Runid */
            runId?: string | null;
            /** Expectedsha256 */
            expectedSha256?: string | null;
        };
        /** Cancellation */
        Cancellation: {
            /** Reason */
            reason?: string | null;
        };
        /** CaseCreate */
        CaseCreate: {
            /** Issueid */
            issueId: string;
            location: components["schemas"]["IncidentLocation"];
            /** Answers */
            answers?: {
                [key: string]: unknown;
            };
            reporter?: components["schemas"]["Reporter"] | null;
        };
        /** CaseEventInput */
        CaseEventInput: {
            /** Kind */
            kind: string;
            /** Message */
            message: string;
            /** Operationid */
            operationId?: string | null;
            /** Runid */
            runId?: string | null;
            /** Attemptid */
            attemptId?: string | null;
            /** Data */
            data?: {
                [key: string]: unknown;
            };
            /**
             * Visibility
             * @default resident
             * @enum {string}
             */
            visibility: "resident" | "presenter";
        };
        /** CasePatch */
        CasePatch: {
            /** Expectedversion */
            expectedVersion: number;
            location?: components["schemas"]["IncidentLocation"] | null;
            /** Answers */
            answers?: {
                [key: string]: unknown;
            } | null;
            reporter?: components["schemas"]["Reporter"] | null;
        };
        /** CaseView */
        CaseView: {
            /** Id */
            id: string;
            /** Version */
            version: number;
            /** Issueid */
            issueId: string;
            location: components["schemas"]["IncidentLocation"];
            /** Answers */
            answers: {
                [key: string]: unknown;
            };
            reporter?: components["schemas"]["Reporter"] | null;
            /** Stage */
            stage: string;
            /** Route */
            route: {
                [key: string]: unknown;
            };
            /** Pendingquestions */
            pendingQuestions?: components["schemas"]["Question"][];
            /** Approvedversion */
            approvedVersion?: number | null;
            /** Currentoperationid */
            currentOperationId?: string | null;
            /** Receipt */
            receipt?: {
                [key: string]: unknown;
            } | null;
            /**
             * Createdat
             * Format: date-time
             */
            createdAt: string;
            /**
             * Updatedat
             * Format: date-time
             */
            updatedAt: string;
            /** Cancelledat */
            cancelledAt?: string | null;
            /** Runid */
            runId: string;
            /** Questionnaireversion */
            questionnaireVersion?: string | null;
        };
        /** CatalogueNode */
        CatalogueNode: {
            /** Id */
            id: string;
            /** Slug */
            slug: string;
            /** Label */
            label: string;
            /** Description */
            description: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "category" | "group" | "issue";
            /** Available */
            available: boolean;
            /** Disabledreason */
            disabledReason?: string | null;
            /** Questionschemaid */
            questionSchemaId?: string | null;
            /** Children */
            children?: components["schemas"]["CatalogueNode"][];
        };
        /** CatalogueView */
        CatalogueView: {
            /** Version */
            version: string;
            /** Categories */
            categories: components["schemas"]["CatalogueNode"][];
            /** Demolocations */
            demoLocations: {
                [key: string]: unknown;
            }[];
            /** Disclaimer */
            disclaimer: string;
        };
        /** Coordinates */
        Coordinates: {
            /** Latitude */
            latitude: number;
            /** Longitude */
            longitude: number;
        };
        /** FaultRequest */
        FaultRequest: {
            /**
             * Kind
             * @default kill_after_acceptance
             * @constant
             */
            kind: "kill_after_acceptance";
            /**
             * Armed
             * @default true
             */
            armed: boolean;
        };
        /** FollowUpAnswer */
        FollowUpAnswer: {
            /** Expectedversion */
            expectedVersion: number;
            /** Answers */
            answers: {
                [key: string]: unknown;
            };
        };
        /** FollowUpInspectionRequest */
        FollowUpInspectionRequest: {
            /** Sourceeventid */
            sourceEventId: string;
            /** Reason */
            reason: string;
            /** Externalticketid */
            externalTicketId: string;
            /** Operationid */
            operationId: string;
            /** Withholdlessonids */
            withholdLessonIds?: string[];
        };
        /** FollowUpRequest */
        FollowUpRequest: {
            /** Sourceeventid */
            sourceEventId: string;
            /** Questionids */
            questionIds: string[];
            /** Reason */
            reason: string;
            /** Externalticketid */
            externalTicketId?: string | null;
            /** Operationid */
            operationId?: string | null;
        };
        /** FormField */
        FormField: {
            /** Id */
            id: string;
            /** Label */
            label: string;
            /**
             * Type
             * @default text
             */
            type: string;
            /**
             * Required
             * @default false
             */
            required: boolean;
            /** Options */
            options?: string[];
        };
        /** FormSnapshot */
        FormSnapshot: {
            /** Id */
            id: string;
            /** Authorityid */
            authorityId: string;
            /** Procedureid */
            procedureId: string;
            /** Url */
            url: string;
            /**
             * Observedat
             * Format: date-time
             */
            observedAt: string;
            /** Sourceversion */
            sourceVersion: string;
            /** Fields */
            fields?: components["schemas"]["FormField"][];
            /** Artifactids */
            artifactIds?: string[];
            /** Sourceids */
            sourceIds?: string[];
            /** Gaps */
            gaps?: string[];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HeartbeatRequest */
        HeartbeatRequest: {
            /** Workerid */
            workerId: string;
            /** Leasetoken */
            leaseToken: string;
            /**
             * Leaseseconds
             * @default 90
             */
            leaseSeconds: number;
        };
        /** IncidentLocation */
        IncidentLocation: {
            /** Municipalityid */
            municipalityId: string;
            /** Uppertierid */
            upperTierId?: string | null;
            /** Incidentaddress */
            incidentAddress: string;
            /** Fixtureid */
            fixtureId?: string | null;
            /**
             * Confirmed
             * @default false
             */
            confirmed: boolean;
            /** Reportermunicipalityid */
            reporterMunicipalityId?: string | null;
            /** Latitude */
            latitude?: number | null;
            /** Longitude */
            longitude?: number | null;
        };
        /** InspectionResult */
        InspectionResult: {
            /** Workerid */
            workerId: string;
            /** Leasetoken */
            leaseToken: string;
            /**
             * Status
             * @enum {string}
             */
            status: "needs_input" | "needs_assistance" | "ready";
            /** Questionids */
            questionIds?: string[];
            /** Reason */
            reason: string;
            /** Evidence */
            evidence?: {
                [key: string]: unknown;
            };
        };
        /** LeaseRequest */
        LeaseRequest: {
            /** Workerid */
            workerId: string;
            /**
             * Leaseseconds
             * @default 90
             */
            leaseSeconds: number;
            /** Jobid */
            jobId?: string | null;
            /** Caseid */
            caseId?: string | null;
        };
        /** LessonRetrievalRequest */
        LessonRetrievalRequest: {
            /** Query */
            query: string;
            /** Authorityid */
            authorityId: string;
            /** Issueid */
            issueId: string;
            /**
             * Categoryid
             * @default roads
             * @enum {string}
             */
            categoryId: "roads" | "graffiti";
            /**
             * Limit
             * @default 3
             */
            limit: number;
            /** Portalid */
            portalId: string;
            /** Formfamily */
            formFamily: string;
            /** Formversion */
            formVersion: number;
            /**
             * Workflowkind
             * @default ticket_update
             */
            workflowKind: string;
            /** Withholdlessonids */
            withholdLessonIds?: string[] | null;
        };
        /** Municipality */
        Municipality: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * Type
             * @enum {string}
             */
            type: "upper-tier" | "lower-tier" | "single-tier";
            /** Parentid */
            parentId?: string | null;
            /** Memberids */
            memberIds?: string[];
            /** Officialurl */
            officialUrl: string;
            /** Population */
            population?: number | null;
            /** Populationyear */
            populationYear?: number | null;
            /** Populationsourceids */
            populationSourceIds?: string[];
            /** Selectionrank */
            selectionRank?: number | null;
            /** Sourceids */
            sourceIds?: string[];
            /**
             * Sourceversion
             * @default 1
             */
            sourceVersion: string;
            /** Boundary */
            boundary?: {
                [key: string]: unknown;
            } | null;
        };
        /** OperationTransition */
        OperationTransition: {
            /** Workerid */
            workerId: string;
            /** Leasetoken */
            leaseToken: string;
            /** Jobid */
            jobId: string;
            /** Expectedstate */
            expectedState: string;
            /**
             * State
             * @enum {string}
             */
            state: "prepared" | "dispatch_started" | "outcome_unknown" | "reconciling" | "receipt_verified" | "needs_assistance" | "stopped";
            /** Runid */
            runId?: string | null;
            /** Attemptid */
            attemptId?: string | null;
            /** Evidence */
            evidence?: {
                [key: string]: unknown;
            };
        };
        /** Question */
        Question: {
            /** Id */
            id: string;
            /**
             * Type
             * @enum {string}
             */
            type: "select" | "text" | "textarea" | "date";
            /** Label */
            label: string;
            /** Required */
            required: boolean;
            /**
             * Description
             * @default
             */
            description: string;
            /** Options */
            options?: components["schemas"]["QuestionOption"][];
            /** Minlength */
            minLength?: number | null;
            /** Maxlength */
            maxLength?: number | null;
            visibleWhen?: components["schemas"]["VisibilityCondition"] | null;
        };
        /** QuestionOption */
        QuestionOption: {
            /** Value */
            value: string;
            /** Label */
            label: string;
            /**
             * Urgenthandoff
             * @default false
             */
            urgentHandoff: boolean;
        };
        /** Questionnaire */
        Questionnaire: {
            /** Issueid */
            issueId: string;
            /** Version */
            version: string;
            /** Questions */
            questions: components["schemas"]["Question"][];
        };
        /** Receipt */
        Receipt: {
            /**
             * Schemaversion
             * @default 1
             * @constant
             */
            schemaVersion: 1;
            /** Ticketid */
            ticketId: string;
            /** Receiptid */
            receiptId: string;
            /** Runid */
            runId: string;
            /**
             * Portalid
             * @enum {string}
             */
            portalId: "roads" | "graffiti";
            /** Clientreference */
            clientReference: string;
            /** Payloaddigest */
            payloadDigest: string;
            /**
             * Action
             * @enum {string}
             */
            action: "create" | "update";
            /**
             * Acceptedat
             * Format: date-time
             */
            acceptedAt: string;
            /** Receipturl */
            receiptUrl: string;
            /** Ticketurl */
            ticketUrl: string;
            /** Artifactid */
            artifactId?: string | null;
            /** Updateurl */
            updateUrl?: string | null;
            /** Formpayloaddigest */
            formPayloadDigest?: string | null;
            /** Formversion */
            formVersion?: number | null;
            /** Receiptsignature */
            receiptSignature?: string | null;
            /** Authorityid */
            authorityId?: string | null;
            /** Routeid */
            routeId?: string | null;
            /** Formsnapshotdigest */
            formSnapshotDigest?: string | null;
            /**
             * Isdemo
             * @default true
             * @constant
             */
            isDemo: true;
        };
        /** ReceiptRecord */
        ReceiptRecord: {
            /** Workerid */
            workerId: string;
            /** Leasetoken */
            leaseToken: string;
            /** Jobid */
            jobId: string;
            receipt: components["schemas"]["Receipt"];
            /** Runid */
            runId?: string | null;
            /** Attemptid */
            attemptId?: string | null;
        };
        /** Reporter */
        Reporter: {
            /** Name */
            name?: string | null;
            /** Email */
            email?: string | null;
            /**
             * Contactconsent
             * @default false
             */
            contactConsent: boolean;
        };
        /** ResearchBatch */
        ResearchBatch: {
            /**
             * Schemaversion
             * @default 1.0
             * @constant
             */
            schemaVersion: "1.0";
            /** Batchid */
            batchId: string;
            /** Municipalities */
            municipalities?: components["schemas"]["Municipality"][];
            /** Sources */
            sources?: components["schemas"]["SourceReference"][];
            /** Procedures */
            procedures?: components["schemas"]["ServiceProcedure"][];
            /** Formsnapshots */
            formSnapshots?: components["schemas"]["FormSnapshot"][];
            /** Artifacts */
            artifacts?: components["schemas"]["ArtifactUpload"][];
            /** Coverage */
            coverage?: {
                [key: string]: unknown;
            }[];
            /** Gaps */
            gaps?: string[];
        };
        /** RetrievalRequest */
        RetrievalRequest: {
            /** Query */
            query: string;
            /** Authorityid */
            authorityId: string;
            /** Issueid */
            issueId: string;
            /**
             * Categoryid
             * @default roads
             * @enum {string}
             */
            categoryId: "roads" | "graffiti";
            /**
             * Limit
             * @default 3
             */
            limit: number;
        };
        /** RouteDecision */
        RouteDecision: {
            /** Supported */
            supported: boolean;
            /** Reason */
            reason: string;
            /** Route */
            route?: {
                [key: string]: unknown;
            } | null;
            /** Missinganswers */
            missingAnswers?: string[];
            /**
             * Urgenthandoff
             * @default false
             */
            urgentHandoff: boolean;
            /**
             * Demo
             * @default true
             */
            demo: boolean;
        };
        /** RoutePreview */
        RoutePreview: {
            /** Issueid */
            issueId: string;
            location: components["schemas"]["IncidentLocation"];
            /** Answers */
            answers?: {
                [key: string]: unknown;
            };
        };
        /** ServiceProcedure */
        ServiceProcedure: {
            /** Id */
            id: string;
            /** Authorityid */
            authorityId: string;
            /** Title */
            title: string;
            /**
             * Categoryid
             * @default roads
             * @enum {string}
             */
            categoryId: "roads" | "graffiti";
            /** Issueids */
            issueIds: string[];
            /** Sourceids */
            sourceIds: string[];
            /** Sourceversion */
            sourceVersion: string;
            /** Retrievaltext */
            retrievalText: string;
            /** Responsibilityrules */
            responsibilityRules?: string[];
            /** Requiredfacts */
            requiredFacts?: string[];
            /** Steps */
            steps?: string[];
            /** Constraints */
            constraints?: string[];
            /** Followupinstructions */
            followUpInstructions?: string[];
            /** Officialformurl */
            officialFormUrl?: string | null;
            /** Contactemail */
            contactEmail?: string | null;
            /** Contactphone */
            contactPhone?: string | null;
            /** Formsnapshotids */
            formSnapshotIds?: string[];
            /** Artifactids */
            artifactIds?: string[];
            /** Coverage */
            coverage?: {
                [key: string]: string;
            };
            /** Gaps */
            gaps?: string[];
            /**
             * Visibility
             * @default public
             * @constant
             */
            visibility: "public";
            /**
             * Verificationstatus
             * @default verified
             * @enum {string}
             */
            verificationStatus: "verified" | "partial";
            /**
             * Current
             * @default true
             */
            current: boolean;
            /**
             * Researchstatus
             * @default verified
             * @enum {string}
             */
            researchStatus: "verified" | "partial";
            /**
             * Searchstatus
             * @default pending
             * @enum {string}
             */
            searchStatus: "pending" | "ready" | "failed";
            /**
             * Integrationstatus
             * @default research_only
             * @enum {string}
             */
            integrationStatus: "research_only" | "demo_tested";
            /**
             * Verifiedat
             * Format: date-time
             */
            verifiedAt: string;
            /** Validuntil */
            validUntil?: string | null;
        };
        /** SourceReference */
        SourceReference: {
            /** Id */
            id: string;
            /** Authorityid */
            authorityId: string;
            /** Url */
            url: string;
            /** Title */
            title: string;
            /**
             * Retrievedat
             * Format: date-time
             */
            retrievedAt: string;
            /** Verifiedat */
            verifiedAt?: string | null;
            /**
             * Extractedtext
             * @default
             */
            extractedText: string;
            /** Contenthash */
            contentHash?: string | null;
            /**
             * Sourceversion
             * @default 1
             */
            sourceVersion: string;
            /** Artifactids */
            artifactIds?: string[];
            /** Gaps */
            gaps?: string[];
            /**
             * Verificationstatus
             * @default verified
             * @enum {string}
             */
            verificationStatus: "verified" | "partial" | "unavailable";
        };
        /** TimelineView */
        TimelineView: {
            /** Events */
            events: {
                [key: string]: unknown;
            }[];
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
            /** Input */
            input?: unknown;
            /** Context */
            ctx?: Record<string, never>;
        };
        /** VerifyRecordRequest */
        VerifyRecordRequest: {
            /**
             * Collection
             * @enum {string}
             */
            collection: "service_procedures" | "procedural_lessons";
            /** Id */
            id: string;
            /** Expectedsourceversion */
            expectedSourceVersion?: string | null;
        };
        /** VisibilityCondition */
        VisibilityCondition: {
            /** Questionid */
            questionId: string;
            /** Equals */
            equals: unknown;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    healthz_healthz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    readyz_readyz_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    session_v1_session_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    catalogue_v1_catalogue_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogueView"];
                };
            };
        };
    };
    questions_v1_questions__issue_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                issue_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Questionnaire"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    locations_v1_locations_resolve_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Coordinates"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    route_preview_v1_routes_preview_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoutePreview"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RouteDecision"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_case_v1_cases_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_case_v1_cases__case_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    edit_case_v1_cases__case_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CasePatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    approve_v1_cases__case_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApprovalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    follow_up_v1_cases__case_id__follow_up_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FollowUpAnswer"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_v1_cases__case_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Cancellation"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    timeline_v1_cases__case_id__timeline_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TimelineView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resident_evidence_v1_cases__case_id__evidence_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    internal_case_internal_v1_cases__case_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    internal_version_internal_v1_cases__case_id__versions__version__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
                version: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    internal_operation_internal_v1_operations__operation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    lease_internal_v1_jobs_lease_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LeaseRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    heartbeat_internal_v1_jobs__job_id__heartbeat_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HeartbeatRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    abandon_internal_v1_jobs__job_id__abandon_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AbandonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    inspection_result_internal_v1_jobs__job_id__inspection_result_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InspectionResult"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    transition_internal_v1_operations__operation_id__transition_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OperationTransition"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    receipt_internal_v1_operations__operation_id__receipt_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReceiptRecord"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    fault_internal_v1_operations__operation_id__fault_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FaultRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    event_internal_v1_cases__case_id__events_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseEventInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    evidence_internal_v1_cases__case_id__evidence_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    follow_up_request_internal_v1_cases__case_id__follow_up_request_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FollowUpRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    follow_up_inspection_internal_v1_cases__case_id__follow_up_inspection_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FollowUpInspectionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    import_research_internal_v1_research_import_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResearchBatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    import_status_internal_v1_research_imports__batch_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                batch_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    upload_artifact_internal_v1_artifacts_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ArtifactUpload"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    artifact_metadata_internal_v1_artifacts__artifact_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                artifact_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    artifact_content_internal_v1_artifacts__artifact_id__content_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                artifact_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retrieve_procedures_internal_v1_retrieval_procedures_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RetrievalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    retrieve_lessons_internal_v1_retrieval_lessons_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LessonRetrievalRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    promote_lesson_internal_v1_retrieval_lessons_promote_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    [key: string]: unknown;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    verify_record_internal_v1_retrieval_verify_record_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VerifyRecordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    mail_status_internal_v1_mail_status_get: {
        parameters: {
            query?: {
                case_id?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    mail_poll_internal_v1_mail_poll_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
}
