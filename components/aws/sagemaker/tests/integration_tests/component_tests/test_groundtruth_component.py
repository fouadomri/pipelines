import pytest
import os
import utils
from utils import kfp_client_utils
from utils import sagemaker_utils
from test_workteam_component import create_workteamjob


@pytest.mark.parametrize(
    "test_file_dir",
    [
        pytest.param(
            "resources/config/image-classification-groundtruth",
            marks=pytest.mark.canary_test,
        )
    ],
)
def test_groundtruth_labeling_job(
    kfp_client, experiment_id, region, sagemaker_client, test_file_dir
):

    download_dir = utils.mkdir(os.path.join(test_file_dir + "/generated"))
    test_params = utils.load_params(
        utils.replace_placeholders(
            os.path.join(test_file_dir, "config.yaml"),
            os.path.join(download_dir, "config.yaml"),
        )
    )

    # First create a workteam using a separate pipeline and get the name, arn of the workteam created.
    workteam_name, _ = create_workteamjob(
        kfp_client,
        experiment_id,
        region,
        sagemaker_client,
        "resources/config/create-workteam",
        download_dir,
    )

    test_params["Arguments"][
        "workteam_arn"
    ] = workteam_arn = sagemaker_utils.get_workteam_arn(sagemaker_client, workteam_name)

    # Generate the ground_truth_train_job_name based on the workteam which will be used for labeling.
    test_params["Arguments"][
        "ground_truth_train_job_name"
    ] = ground_truth_train_job_name = (
        test_params["Arguments"]["ground_truth_train_job_name"] + "-by-" + workteam_name
    )

    _ = kfp_client_utils.compile_run_monitor_pipeline(
        kfp_client,
        experiment_id,
        test_params["PipelineDefinition"],
        test_params["Arguments"],
        download_dir,
        test_params["TestName"],
        test_params["Timeout"],
        test_params["StatusToCheck"],
    )

    # Verify the GroundTruthJob was created in SageMaker and is InProgress.
    # TODO: Add a bot to complete the labeling job and check for completion instead.
    try:
        response = sagemaker_utils.describe_labeling_job(
            sagemaker_client, ground_truth_train_job_name
        )
        assert response["LabelingJobStatus"] == "InProgress"

        # Verify that the workteam has the specified labeling job
        labeling_jobs = sagemaker_utils.list_labeling_jobs_for_workteam(
            sagemaker_client, workteam_arn
        )
        assert len(labeling_jobs["LabelingJobSummaryList"]) == 1
        assert (
            labeling_jobs["LabelingJobSummaryList"][0]["LabelingJobName"]
            == ground_truth_train_job_name
        )
    finally:
        # Cleanup the SageMaker Resources
        sagemaker_utils.stop_labeling_job(sagemaker_client, ground_truth_train_job_name)
        sagemaker_utils.delete_workteam(sagemaker_client, workteam_name)

    # Delete generated files
    utils.remove_dir(download_dir)
