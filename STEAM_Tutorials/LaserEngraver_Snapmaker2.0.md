# Laser Engraving — Snapmaker 2.0

## What is Laser Engraving?

Laser engraving uses a focused laser to mark a design onto a material. This can include text, logos, photographs, and other artwork.

The STEAM Room uses Snapmaker 2.0 equipment for laser engraving. Projects can include compatible business cards, wooden frames, and other materials approved for the laser.

## Who Can Use the Laser Engraver?

Laser engraving in the STEAM Room is free for students, faculty, staff, and members of the public.

Ask Adam Abbadusky, the STEAM Specialist, for help preparing and running a project. The process involves setting the laser height, positioning the design, and choosing settings for the material.

## What Software Do We Use?

The STEAM Room uses Snapmaker Luban and LightBurn together.

- **Snapmaker Luban:** Used first to set the laser head height based on the material thickness.
- **LightBurn:** Used to prepare the engraving settings and run the actual engraving.

In the current STEAM Room setup, LightBurn does not handle the laser height adjustment, so that part is done through Luban first.

## Preparing an Engraving

### 1. Prepare the Image

Start by modifying the requested image to fit the object being engraved.

A business card and a wooden frame need different image dimensions. They also need different engraving settings because the materials react differently to the laser.

Check the design’s size and proportions before moving on. Resizing an image without keeping its proportions can stretch or distort it.

### 2. Position the Material

Place the object in the correct position on the engraving bed. Make sure it sits flat and will stay in place during the engraving.

The object’s placement needs to match where the design will run.

Close the enclosure before continuing.

### 3. Set the Laser Height Through Luban

Open Snapmaker Luban and connect it to the laser engraver.

In Adam’s current workflow, he loads a previously prepared G-code file and selects Start to bring up the material thickness prompt.

Enter the thickness of the actual material being engraved. For the business cards used in this workflow, Adam enters **0.2 mm**. This is specific to those cards and should not be used for every material.

The machine uses the entered thickness to position the laser head at the appropriate height.

### 4. Switch From Luban to LightBurn

In Adam’s current workflow, he disconnects Luban as the laser head begins lowering, closes Luban, and then opens LightBurn.

**This handoff needs Adam’s supervision. Disconnecting the application is not confirmation that the loaded job has stopped. Before continuing, confirm that no Luban job remains active and the laser is off.**

Connect LightBurn to the laser engraver.

### 5. Return to the Engraving Origin

After connecting, Adam uses the LightBurn control that returns the machine to the engraving’s XY starting position.

In the current room setup, the engraving starts at **X = 0, Y = 0**, while keeping the laser at the height established through Luban.

The XY starting position and the laser’s Z height are separate settings. Ask Adam to demonstrate the correct control for this setup.

### 6. Adjust the Image in LightBurn

Once the machine is positioned, finish adjusting the image in LightBurn.

Settings can include:

- Image size and placement.
- Sharpness.
- Brightness and contrast.
- Resolution.
- Engraving speed.
- Laser power.
- Image processing mode.

The best settings depend on the material and the appearance you want. A setting that works on a business card may not work on a wooden frame.

## Choosing an Image Mode

### Jarvis

Jarvis is a dithering option that represents shading through a pattern of dots.

Adam often finds that it works well for detailed images, including photographs of people.

### Grayscale

Grayscale varies the laser power to represent different shades.

It can also work well for photographs, but the minimum and maximum power settings may need more adjustment to get useful detail without making the engraving too dark.

### Other Dithering Options

LightBurn has other dithering options that produce different dot patterns.

There is no single mode that works best for every image and material. Experimenting on a suitable test piece can help you choose the settings before engraving the final object.

## Starting the Engraving

Before selecting Start, check that:

- The design fits the object.
- The material is positioned correctly.
- The laser height and XY starting position are correct.
- The speed and power settings suit the material.
- The enclosure is fully closed.
- The ventilation is operating.

Once everything is ready, start the engraving through LightBurn.

Keep the enclosure closed during operation and stay with the machine while it runs.

## When the Engraving is Finished

In the current STEAM Room setup, the machine returns to the engraving’s **X = 0, Y = 0** position when the job finishes. The laser head remains at the engraving height.

Use the **Home control on the Snapmaker touchscreen** to return the machine to its home position and raise the head.

Wait until the movement has finished and the laser is off before opening the enclosure and removing the object.

## Basic Troubleshooting

### The Engraving Is Too Dark

The power may be too high or the movement too slow for the material. The image adjustments can also make the result darker.

Ask Adam to help adjust the settings and test again.

### The Engraving Is Too Light

The power may be too low, the movement too fast, or the laser height incorrect.

Check the setup before increasing the power.

### Details Are Missing

The image size, contrast, resolution, or processing mode may need adjustment.

Try comparing Jarvis with grayscale on a test piece. For grayscale, the minimum and maximum power settings may also need changing.

### The Design Is Engraving in the Wrong Place

Stop the job and check the material placement, design position, and XY starting position.

Do not move the object while the engraving is running.

### Luban or LightBurn Cannot Connect

In the STEAM Room setup, this usually means another application is already using the machine’s connection.

For example:

If LightBurn is open before you connect through Snapmaker Luban, Luban may fail to connect.

If Cura is open, it can also prevent Luban from connecting.

If Luban still has the connection, LightBurn may fail to connect.

Close the other applications, then try connecting again through the application you need.

For the normal engraving workflow, start with Cura and LightBurn closed. Connect through Luban to set the laser height. When that step is finished, disconnect and close Luban before opening and connecting through LightBurn.

If it still will not connect, ask Adam for help.

## Material and Equipment Safety

Only use materials approved for laser engraving. Some plastics, coatings, and unknown materials can release hazardous fumes or damage the equipment.

Keep the enclosure closed, use the ventilation, and do not leave an engraving unattended.

If you see flames or anything unusual, stop the job and get Adam.

## Need Help?

Ask Adam if you need help preparing an image, checking a material, setting the laser height, switching between applications, or choosing engraving settings.