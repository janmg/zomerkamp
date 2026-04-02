I want a task roster application in python for a 4 day event, which takes fairness, availability and preference into account. Store the data in an mariadb database

One python commandline application should use two csv files, one with tasks listed with a task name, begin time and end time and the amount of points to be earned and the amount of people required. The other csv files should be a list of participants with name, email address, phonenumber and blocks of time (morning, afternoon, evening) where people are available to help and a multiple choice preference for an activity like "serving snacks", "serving food", "cleaning after food", "cleaning toilets", "organize afternoon games" or if nothing select "do not care". include a free text remarks field.

The second python commandline application should schedule based on fairness and availability. Make it possible to export the tables as csv. Nominate one person to be the lead for a task. Once the schedule is calculated. Add a new person as backup, select the person who has the least amount of effort points and who is available. The backup does not score points for being a backup.

The third applications is for admins, to select a person, who is unavailable for a task or for a day or for all days. Select the backup for each task, award this person points for the fairness and based on fairness select a new backup based on fairness.

The fourth application is a flask application that based on the url shows a list of people ordered by points earned by doing the tasks. Another url should show a table of all people in alphabetical order with a list of tasks with timeslot and a third url should show one master sheet with all activities ordered by time and assigned people. This last one should show all data.
