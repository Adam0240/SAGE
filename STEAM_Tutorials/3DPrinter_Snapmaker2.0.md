# 3D Printing — Snapmaker 2.0

## What is a 3D Printer?

A 3D printer takes a digital model and turns it into a physical object. It does this by heating plastic filament and placing it down one layer at a time until the object is finished.

The STEAM Room has two Snapmaker 2.0 A350 machines. These machines have interchangeable toolheads for different jobs. For 3D printing, the machine needs its 3D printing module and printing bed installed.

## Who Can Use the Printers?

3D printing in the STEAM Room is free for students, faculty, staff, and members of the public.

If you have never used a 3D printer before, ask Adam Abbadusky, the STEAM Specialist, for help getting started.

## What Can I Print?

Some examples include:

- Keychains and small decorations.
- Models for class projects.
- Educational models.
- Custom parts and prototypes.

Whether something can be printed depends on its size, shape, material requirements, and the amount of time needed. Some models need changes before they will print correctly.

If you are unsure whether your idea will work, ask Adam before preparing the print.

## What Files Do I Need?

You need a digital 3D model. STL is a common file format used for 3D printing.

The model must then be prepared in a program called a slicer. The slicer turns the model into instructions called G-code that tell the printer how to make the object.

An STL file is the model. A G-code file contains the printing instructions.

G-code needs to be prepared for the correct printer, material, and settings. A file prepared for another printer may not work correctly on the Snapmaker.

## What Software Do We Use?

The STEAM Room uses Cura and OctoPrint as part of the printing workflow.

- **Cura:** Prepares the model and creates the G-code file.
- **OctoPrint:** Sends the G-code instructions to the printer and lets you start, monitor, pause, or cancel the print through a web browser.

## Preparing a Print

### 1. Choose a Model

Start with a model you created or downloaded. Check that it is the object you want and that its size makes sense for your project.

### 2. Prepare the Model in Cura

Open the model in Cura and select the correct printer profile and material settings.

In the slicer, the model can be positioned, rotated, and resized. Settings such as layer height, infill, and supports affect how the finished object looks and how long it takes to print.

- **Layer height:** Controls the thickness of each printed layer.
- **Infill:** Controls the internal structure of the object.
- **Supports:** Help hold up sections that would otherwise print over empty space.

Ask Adam for help choosing settings if you are unfamiliar with them.

### 3. Check the Preview

After slicing, look through the preview before starting the print. Check the estimated printing time, model placement, and any supports.

A model looking correct on screen does not always mean it is ready to print.

### 4. Upload the File to OctoPrint

Once you have finished slicing:

1. Save the G-code file from Cura.
2. Open OctoPrint for the printer you plan to use.
3. Upload the G-code file.
4. Select the uploaded file and check that it is the correct one.

Make sure you are connected to the intended printer before starting anything. Preparing and uploading a file does not mean the physical printer is ready.

Ask Adam if you need help accessing OctoPrint or identifying which printer you are controlling.

### 5. Prepare the Printer

Before printing, check that the correct toolhead and bed are installed, the printing surface is clean, and enough of the correct filament is loaded.

If the machine needs calibration or you are unsure whether it is ready, ask Adam for assistance.

### 6. Start the Print

Once the printer is ready and the correct file is selected, start the print through OctoPrint.

Watch the beginning of the print. The first layer should stick to the bed and form the shape shown in the preview.

If the filament is dragging around, collecting around the nozzle, or failing to stick, stop the print and check the problem before continuing.

## Monitoring the Print

OctoPrint lets you check printing progress and printer temperatures. It also provides controls to pause or cancel a print.

Check the physical printer as well. Progress shown on the screen does not guarantee that the object is printing correctly.

If a print has failed, cancel it rather than letting the printer continue wasting material.

## How Long Does Printing Take?

Printing time depends on the size of the model and the settings used. A small object may take less than an hour, while a larger or more detailed object can take several hours or longer.

The slicer provides an estimate, but the actual printing time can vary. Plan ahead if the print is needed for an assignment.

## When the Print is Finished

Let the nozzle and printing bed cool before removing the object. Be careful when removing supports or using tools to separate a print from the bed.

Ask Adam for help if the object is stuck or you are unsure how to remove it.

## Basic Troubleshooting

### The Print Is Not Sticking

Possible causes include a dirty printing surface, incorrect bed leveling, or settings that do not match the material.

Stop the print and check the setup before trying again.

### No Filament Is Coming Out

The filament may have run out, failed to feed, or become blocked. Ask Adam to check the filament path and printing module.

### The Print Looks Like a Pile of String

The object may have come loose from the bed, or part of the model may not have enough support.

Stop the print so the printer does not continue wasting material.

### OctoPrint Is Not Connecting to the Printer

Check that you opened OctoPrint for the intended printer and that the printer is powered on.

In the STEAM Room setup, this usually means another application is already using the printer’s connection.

For example, if Cura is open when you try to connect through OctoPrint, the connection may fail.

Close Cura and any other applications that could be connected to the printer, including Snapmaker Luban or LightBurn.

Try connecting through OctoPrint again.

Only have the application you are using to control the printer connected at that time. If it still will not connect, ask Adam for help.

Ask Adam to check the connection if the printer remains unavailable.

## Need Help?

Ask Adam if you need help finding a model, preparing a file, using OctoPrint, choosing settings, or troubleshooting a failed print.

The nozzle and bed become hot during operation. Keep your hands clear of hot parts and moving components.