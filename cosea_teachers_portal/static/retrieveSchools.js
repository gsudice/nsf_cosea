// document.addEventListener("DOMContentLoaded", function () {
//     const districtDropdown = document.getElementById("district-dropdown");
//     const schoolDropdown = document.getElementById("school-dropdown");

//     districtDropdown.addEventListener("change", function () {
//         const selectedDistrict = districtDropdown.value;
//         fetch("/get_schools", {
//             method: "POST",
//             headers: {
//                 "Content-Type": "application/x-www-form-urlencoded"
//             },
//             body: `selected_district=${selectedDistrict}`
//         })
//             .then(response => response.json())
//             .then(data => {
//                 schoolDropdown.innerHTML = "<option value=''>Select a school</option>";
//                 data.schools.forEach(school => {
//                     const option = document.createElement("option")
//                     option.value = school;
//                     option.textContent = school;
//                     schoolDropdown.appendChild(option);
//                 });
//             })
//             .catch(error => {
//                 console.error("Error fetching schools:", error);
//         });
//      });
// });

document.getElementById('district-dropdown').addEventListener('change', function() {
    var selectedDistrict = this.value;
    var schoolDropdown = document.getElementById('school-dropdown');
    
    // Clear existing options
    schoolDropdown.innerHTML = '<option value="none" selected disabled hidden>Select an Option</option>';

    // Fetch schools for the selected district
    fetch('/get_schools?district=' + encodeURIComponent(selectedDistrict))
        .then(response => response.json())
        .then(schools => {
            schools.forEach(school => {
                var option = document.createElement('option');
                option.value = school;
                option.textContent = school;
                schoolDropdown.appendChild(option);
            });
        })
        .catch(error => {
            console.error('Error fetching schools:', error);
        });
});
