# Field Production Operator Driving Route Optimization To Maximize Hydrocarbon Production

Oil and gas field operators face a daily challenge determining where to spend their time to have the biggest impact on increasing production.  Production disrupting incidents happen randomly and can occur with any well on any given day. Every morning operators look at each of their well’s production numbers to see if they need to address problems such as an artificial lift device being offline, separator dump valves clogging, plunger lift wells logging off, and many others. Optimizing the driving route based on production decrease and the driving time between wells creates a difficult problem due to the number of different choices. This code sample shows how to use Amazon Location Services, AWS Lambda and the python library [OR-Tools](https://developers.google.com/optimization/introduction/python) to produce optimized driving routes which maximize the volume of production an operator can get back online.


## Architecture
![Diagram](assets/Operator-Routing-Architecture.svg "Architecture")


## Steps to deploy this repository
1. Deploy the template using the [Serverless Application Module](https://aws.amazon.com/serverless/sam/). From the root of this repository execute these bash commands:
    1. `sam build --use-container`
    1. `sam deploy --guided`
1. Look for the cloudformation stack output named `WebEndpoint`. Open this link in a web browser to get an optimized route to maximize production!


## Usage Guidance
The sample code; software libraries; command line tools; proofs of concept; templates; or other related technology (including any of the foregoing that are provided by our personnel) is provided to you as AWS Content under the AWS Customer Agreement, or the relevant written agreement between you and AWS (whichever applies). You should not use this AWS Content in your production accounts, or on production or other critical data. You are responsible for testing, securing, and optimizing the AWS Content, such as sample code, as appropriate for production grade use based on your specific quality control practices and standards. Deploying AWS Content may incur AWS charges for creating or using AWS chargeable resources, such as running Amazon EC2 instances or using Amazon S3 storage.


## Contributing
Please create a new GitHub issue for any feature requests, bugs, or documentation improvements.

Where possible, please also submit a pull request for the change.

## Security
See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License
This library is licensed under the MIT-0 License. See the LICENSE file.
