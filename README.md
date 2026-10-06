# Francis A. Byrne Tee Time Watcher

Checks the Byrne tee sheet every 10 minutes and pushes a notification to your phone
when a Saturday or Sunday tee time between 8:00 AM and 2:00 PM opens up for 4 golfers.
You only get pinged for times that are new since the last check, so the same slot
won't buzz you every 10 minutes. If a booked time gets cancelled and reopens, you'll
hear about it again.

## Setup (about 10 minutes, easiest on a computer)

### 1. Phone alerts (ntfy)
1. Install the **ntfy** app (App Store or Google Play).
2. Tap **+** and subscribe to a topic name that nobody could guess,
   e.g. `byrne-harry-7f3k9q2m`. Anyone who knows the name can read it, so make it random.
3. On iPhone, allow notifications when asked.

### 2. GitHub (runs the checker for free)
1. Create a free account at github.com.
2. Click **New repository**. Name it `byrne-tee-watcher`, choose **Public**, create it.
   (Public keeps it free: private repos get 2,000 free minutes a month and this uses
   about 4,300. Your ntfy topic stays hidden in a secret.)
3. Click **uploading an existing file** and drag in `tee_checker.py`, `state.json`,
   `requirements.txt`, and `README.md`. Commit.
4. Click **Add file > Create new file**. For the name, type
   `.github/workflows/check.yml` exactly, paste in the contents of `check.yml`, commit.
5. Go to **Settings > Secrets and variables > Actions > New repository secret**.
   Name: `NTFY_TOPIC`. Value: your topic name from step 1.
6. Go to **Settings > Actions > General**, scroll to **Workflow permissions**,
   select **Read and write permissions**, save.

### 3. Test it
1. Go to the **Actions** tab, click **Byrne tee time watcher**, then **Run workflow**.
2. Pick **test** and run. Your phone should buzz within a minute.
3. Run it again with **check** and open the log. It lists every matching slot it sees.

From here it runs on its own every 10 minutes.

## If the log says it can't read the tee sheet
The course's online booking may separate times by "booking class" (for example
cardholder vs public). Run the workflow with **discover** to list them. Then go to
**Settings > Secrets and variables > Actions > Variables** and add a variable named
`BOOKING_CLASS` with the number for the class you'd book under.

If it fails for about an hour straight, you'll get one warning push so it never dies silently.

## Changing what it looks for
Edit the settings block at the top of `tee_checker.py`:
`PLAYERS`, `EARLIEST`, `LATEST`, `WEEKEND_DAYS`, `DAYS_AHEAD`.

## Turning it off
**Actions > Byrne tee time watcher > ... > Disable workflow.** The course closes for the
season in late December, so disable it then.

## Notes
- GitHub's scheduler sometimes runs a few minutes late during busy periods.
- It runs around the clock, which matters because new booking days and cancellations can
  show up overnight. Use the ntfy app's per-topic settings if you want quiet hours.
